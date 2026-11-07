import { describe, expect, it } from 'vitest'
import { featureOn, FEATURES, flagVar, offMessage } from './feature-flags'

describe('feature flags', () => {
  it('are all off by default outside tests', () => {
    // D48: voice is on by default; the old wake word, scam analysis and files search stay off.
    for (const f of FEATURES) expect(featureOn(f, {})).toBe(f === 'voice')
  })
  it('turn on only with the exact variable set to 1, and an explicit 0 wins even under vitest', () => {
    expect(featureOn('voice', { UNDERSTUDY_FLAG_VOICE: '1' })).toBe(true)
    expect(featureOn('scam', { UNDERSTUDY_FLAG_SCAM: 'true' })).toBe(false)
    expect(featureOn('voice', { UNDERSTUDY_FLAG_VOICE: '0' })).toBe(false)
    expect(featureOn('scam', { VITEST: 'true' })).toBe(true)
    expect(featureOn('scam', { VITEST: 'true', UNDERSTUDY_FLAG_SCAM: '0' })).toBe(false)
  })
  it('has a plain message per feature and a stable variable name', () => {
    expect(flagVar('wake')).toBe('UNDERSTUDY_FLAG_WAKE')
    for (const f of FEATURES) expect(offMessage(f)).toMatch(/switched off/)
  })
})

describe('experiments (UNDERSTUDY_X_<NAME>)', () => {
  it('are on by default (D48) and off only when set to 0', async () => {
    const { experimentOn, experimentVar } = await import('./feature-flags')
    expect(experimentVar('cue')).toBe('UNDERSTUDY_X_CUE')
    expect(experimentOn('cue', { UNDERSTUDY_X_CUE: '1' })).toBe(true)
    expect(experimentOn('cue', {})).toBe(true)
    expect(experimentOn('cue', { VITEST: 'true' })).toBe(true)
    expect(experimentOn('cue', { UNDERSTUDY_X_CUE: '0' })).toBe(false)
    expect(experimentOn('cue', { VITEST: 'true', UNDERSTUDY_X_CUE: '0' })).toBe(false)
  })
  it('include the Hey Knack listener, separate from the old cloud wake feature flag', async () => {
    const { experimentOn, experimentVar, featureOn } = await import('./feature-flags')
    expect(experimentVar('wake')).toBe('UNDERSTUDY_X_WAKE')
    expect(experimentOn('wake', {})).toBe(true)
    expect(experimentOn('wake', { UNDERSTUDY_X_WAKE: '0' })).toBe(false)
    // The old cloud wake word stays off whatever the new flag says.
    expect(featureOn('wake', { UNDERSTUDY_X_WAKE: '1' })).toBe(false)
  })
})

describe('forced settings', () => {
  it('pin wake and files off until their flags are set', async () => {
    const { forcedSettings } = await import('./feature-flags')
    // D48: Cue is on by default, so it is pinned off only by an explicit UNDERSTUDY_X_CUE=0; wake and files stay pinned off.
    expect(forcedSettings({})).toEqual({ wakeEnabled: false, filesEnabled: false })
    expect(forcedSettings({ UNDERSTUDY_X_CUE: '0' })).toEqual({ wakeEnabled: false, filesEnabled: false, cueEnabled: false })
    expect(forcedSettings({ UNDERSTUDY_FLAG_WAKE: '1' })).toEqual({ filesEnabled: false })
    expect(forcedSettings({ UNDERSTUDY_FLAG_WAKE: '1', UNDERSTUDY_FLAG_FILES: '1' })).toEqual({})
    expect(forcedSettings({ UNDERSTUDY_FLAG_WAKE: '1', UNDERSTUDY_FLAG_FILES: '1', UNDERSTUDY_X_CUE: '1' })).toEqual({})
  })
  it('SettingsStore keeps forced values over saved values and patches', async () => {
    const { SettingsStore } = await import('./settings')
    const store = new SettingsStore(null, { forced: { wakeEnabled: false, filesEnabled: false } })
    expect(store.get().wakeEnabled).toBe(false)
    store.patch({ wakeEnabled: true, filesEnabled: true, captions: false }, { trusted: true })
    expect(store.get()).toMatchObject({ wakeEnabled: false, filesEnabled: false, captions: false })
  })
})
