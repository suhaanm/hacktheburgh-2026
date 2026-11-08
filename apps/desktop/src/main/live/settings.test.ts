import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { DEFAULT_LIVE_SETTINGS, LIVE_CONSENT_VERSION, LiveSettingsStore, coerceLiveSettings, frameConsent, liveConsentPatch, voiceConsent } from './settings'
import { liveFlagOn, liveModelId, speakerFlagOn, transcribeModelId } from './flags'

describe('flags', () => {
  it('voice is on by default (D48) and either the experiment or the feature flag set to 0 turns it off', () => {
    expect(liveFlagOn({})).toBe(true)
    expect(liveFlagOn({ UNDERSTUDY_X_LIVE: '1', UNDERSTUDY_FLAG_VOICE: '1' })).toBe(true)
    expect(liveFlagOn({ UNDERSTUDY_X_LIVE: '0' })).toBe(false)
    expect(liveFlagOn({ UNDERSTUDY_FLAG_VOICE: '0' })).toBe(false)
    expect(liveFlagOn({ UNDERSTUDY_X_LIVE: '0', UNDERSTUDY_FLAG_VOICE: '1' })).toBe(false)
  })
  it('spoken pack lines need UNDERSTUDY_VOICE=1 on top', () => {
    expect(speakerFlagOn({})).toBe(false)
    expect(speakerFlagOn({ UNDERSTUDY_VOICE: '0' })).toBe(false)
    expect(speakerFlagOn({ UNDERSTUDY_VOICE: '1' })).toBe(true)
  })
  it('model ids come from the environment only and are checked for shape', () => {
    expect(liveModelId({})).toBeNull()
    expect(liveModelId({ GEMINI_MODEL_LIVE: 'some-live.model:1' })).toBe('some-live.model:1')
    expect(liveModelId({ GEMINI_MODEL_LIVE: 'bad id/with slash' })).toBeNull()
    expect(liveModelId({ MODEL_LIVE: 'old-name' })).toBe('old-name')
    expect(transcribeModelId({})).toBeNull()
    expect(transcribeModelId({ GEMINI_MODEL_TRANSCRIBE: 'tr-1' })).toBe('tr-1')
  })
})

describe('settings', () => {
  it('voice is switched on by default but nothing is agreed to: no consent record, frames off, with the specified limits', () => {
    expect(DEFAULT_LIVE_SETTINGS).toMatchObject({ liveEnabled: true, liveConsentVersion: 0, liveFrames: false, liveGraceMs: 8000, liveIdleMs: 60_000, liveMaxMs: 300_000, liveFrameIntervalMs: 5000 })
    expect(voiceConsent(DEFAULT_LIVE_SETTINGS)).toBe(false)
    expect(frameConsent(DEFAULT_LIVE_SETTINGS)).toBe(false)
  })
  it('voice needs the current consent text; frames need their own switch as well', () => {
    const s = new LiveSettingsStore(null)
    s.patch({ liveEnabled: true }, { trusted: true })
    expect(voiceConsent(s.get())).toBe(false) // no consent record
    s.patch(liveConsentPatch({ voice: true }, new Date(0)), { trusted: true })
    expect(voiceConsent(s.get())).toBe(true)
    expect(frameConsent(s.get())).toBe(false)
    s.patch(liveConsentPatch({ voice: true, frames: true }), { trusted: true })
    expect(frameConsent(s.get())).toBe(true)
    s.patch({ liveConsentVersion: LIVE_CONSENT_VERSION + 1 }, { trusted: true })
    expect(voiceConsent(s.get())).toBe(false) // an older consent text no longer counts
  })
  it('withdrawing consent switches voice and frames off and clears the record', () => {
    const s = new LiveSettingsStore(null)
    s.patch(liveConsentPatch({ voice: true, frames: true }), { trusted: true })
    s.patch(liveConsentPatch({ voice: false }), { trusted: true })
    expect(s.get()).toMatchObject({ liveEnabled: false, liveFrames: false, liveConsentVersion: 0, liveConsentAt: '' })
  })
  it('an untrusted source can turn things down but never up', () => {
    const s = new LiveSettingsStore(null)
    s.patch(liveConsentPatch({ voice: true, frames: true }), { trusted: true })
    s.patch({ liveEnabled: true, liveFrames: true, liveDailyUsd: 50, liveMaxMs: 300_000, liveFrameIntervalMs: 5000 }) // untrusted: up is ignored
    expect(s.get().liveDailyUsd).toBe(200)
    s.patch({ liveFrames: false, liveDailyUsd: 0.1, liveFrameIntervalMs: 30_000 }) // down is fine
    expect(s.get()).toMatchObject({ liveFrames: false, liveDailyUsd: 0.1, liveFrameIntervalMs: 30_000 })
    s.patch({ liveEnabled: true, liveFrames: true }) // turning back on needs the trusted path
    expect(s.get()).toMatchObject({ liveEnabled: true, liveFrames: false })
    const off = new LiveSettingsStore(null)
    off.patch({ liveEnabled: false }) // down is fine
    expect(off.get().liveEnabled).toBe(false)
    off.patch({ liveEnabled: true }) // and up needs the trusted path
    expect(off.get().liveEnabled).toBe(false)
  })
  it('limits cannot be set outside their ranges: five minutes at most, no frame faster than every five seconds', () => {
    const s = new LiveSettingsStore(null)
    s.patch({ liveMaxMs: 3_600_000, liveFrameIntervalMs: 200, liveGraceMs: 1, liveDailyUsd: -1, liveVoiceName: '../x' }, { trusted: true })
    expect(s.get()).toMatchObject({ liveMaxMs: 300_000, liveFrameIntervalMs: 5000, liveGraceMs: 8000, liveDailyUsd: 200, liveVoiceName: 'Sulafat' })
  })
  it('pause for an hour is allowed from any source and counts as no consent while it lasts', () => {
    let t = 1000
    const s = new LiveSettingsStore(null, () => t)
    s.pauseFor()
    expect(s.get().livePausedUntilMs).toBe(1000 + 3_600_000)
    s.resume()
    expect(s.get().livePausedUntilMs).toBe(0)
  })
  it('persists to live.json (0600, only the settings keys) and reads leniently', () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'live-set-'))
    const s = new LiveSettingsStore(dir)
    s.patch(liveConsentPatch({ voice: true, frames: true, dailyUsd: 0.2 }), { trusted: true })
    const file = path.join(dir, 'live.json')
    expect(fs.statSync(file).mode & 0o777).toBe(0o600)
    const saved = JSON.parse(fs.readFileSync(file, 'utf8'))
    expect(Object.keys(saved).sort()).toEqual(Object.keys(DEFAULT_LIVE_SETTINGS).sort())
    expect(new LiveSettingsStore(dir).get().liveDailyUsd).toBe(0.2)
    fs.writeFileSync(file, '{"liveEnabled":"yes","liveDailyUsd":1,"junk":1}')
    expect(coerceLiveSettings(JSON.parse(fs.readFileSync(file, 'utf8')))).toMatchObject({ liveEnabled: true, liveDailyUsd: 1 }) // a bad value falls back to the default (on); the consent record is separate
    fs.writeFileSync(file, 'not json')
    expect(new LiveSettingsStore(dir).get()).toEqual(DEFAULT_LIVE_SETTINGS)
  })
})
