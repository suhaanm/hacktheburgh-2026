import { describe, expect, it } from 'vitest'
import { featureOn, FEATURES, flagVar, offMessage } from './feature-flags'

describe('feature flags', () => {
  it('are all off by default outside tests', () => {
    for (const f of FEATURES) expect(featureOn(f, {})).toBe(false)
  })
  it('turn on only with the exact variable set to 1, and an explicit 0 wins even under vitest', () => {
    expect(featureOn('voice', { UNDERSTUDY_FLAG_VOICE: '1' })).toBe(true)
    expect(featureOn('voice', { UNDERSTUDY_FLAG_VOICE: 'true' })).toBe(false)
    expect(featureOn('scam', { VITEST: 'true' })).toBe(true)
    expect(featureOn('scam', { VITEST: 'true', UNDERSTUDY_FLAG_SCAM: '0' })).toBe(false)
  })
  it('has a plain message per feature and a stable variable name', () => {
    expect(flagVar('wake')).toBe('UNDERSTUDY_FLAG_WAKE')
    for (const f of FEATURES) expect(offMessage(f)).toMatch(/switched off/)
  })
})
