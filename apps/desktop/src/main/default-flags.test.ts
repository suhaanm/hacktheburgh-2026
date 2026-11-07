import { describe, expect, it } from 'vitest'
import { applyDesktopDefaultFlags, DESKTOP_DEFAULT_ON } from './default-flags'

describe('desktop default flags (D48)', () => {
  it('turns every listed flag on when nothing is set', () => {
    const env: Record<string, string | undefined> = {}
    expect(applyDesktopDefaultFlags(env).sort()).toEqual([...DESKTOP_DEFAULT_ON].sort())
    for (const n of DESKTOP_DEFAULT_ON) expect(env[n]).toBe('1')
  })
  it('keeps an explicit 0 and an explicit 1, and fills an empty value', () => {
    const env: Record<string, string | undefined> = { UNDERSTUDY_VOICE: '0', UNDERSTUDY_X_CUE: '1', UNDERSTUDY_X_LIVE: '' }
    applyDesktopDefaultFlags(env)
    expect(env.UNDERSTUDY_VOICE).toBe('0')
    expect(env.UNDERSTUDY_X_CUE).toBe('1')
    expect(env.UNDERSTUDY_X_LIVE).toBe('1')
  })
  it('never defaults a real-desktop arm switch, the legacy remote path, or the guards', () => {
    const env: Record<string, string | undefined> = {}
    applyDesktopDefaultFlags(env)
    for (const n of ['UNDERSTUDY_REAL_ACTUATOR', 'ALONGSIDE_AGENCY_LOOP', 'UNDERSTUDY_JXA_CLICK', 'UNDERSTUDY_LEGACY_REMOTE', 'UNDERSTUDY_FLAG_WAKE', 'UNDERSTUDY_FLAG_SCAM', 'UNDERSTUDY_FLAG_FILES', 'UNDERSTUDY_VOICE_DEBUG_TEXT', 'UNDERSTUDY_CU_FRAME_HINT'])
      expect(env[n]).toBeUndefined()
  })
})
