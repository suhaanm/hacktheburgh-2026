import { describe, expect, it } from 'vitest'
import { describeRow, screenNeedsRestart, type PermissionStatus } from './permissions'

const status = (over: Partial<PermissionStatus> = {}): PermissionStatus => ({ microphone: 'not-determined', screen: 'not-determined', accessibility: false, probe: 'skipped', needsRestart: false, hint: '', ...over })

describe('permission rows', () => {
  it('shows a tick and no action once allowed', () => {
    const row = describeRow('microphone', status({ microphone: 'granted' }))
    expect(row).toMatchObject({ granted: true, chip: 'Allowed', action: 'none' })
    expect(describeRow('accessibility', status({ accessibility: true }))).toMatchObject({ granted: true, action: 'none' })
  })

  it('microphone: asks first, opens System Settings once it has been refused', () => {
    expect(describeRow('microphone', status())).toMatchObject({ action: 'request', actionLabel: 'Allow the microphone' })
    expect(describeRow('microphone', status({ microphone: 'denied' }))).toMatchObject({ chip: 'Blocked', action: 'open', actionLabel: 'Open Microphone settings' })
    expect(describeRow('microphone', null)).toMatchObject({ action: 'request' })
  })

  it('screen: prompt when undecided, settings when blocked, restart when macOS needs it', () => {
    expect(describeRow('screen', status())).toMatchObject({ action: 'request' })
    expect(describeRow('screen', status({ screen: 'denied' }))).toMatchObject({ action: 'open', actionLabel: 'Open Screen Recording settings' })
    expect(describeRow('screen', status({ screen: 'granted', needsRestart: true }))).toMatchObject({ granted: false, action: 'restart', actionLabel: 'Restart now' })
    expect(describeRow('screen', null)).toMatchObject({ action: 'open', chip: 'Not checked yet' })
    expect(describeRow('screen', status({ screen: 'granted', probe: 'empty' }), { restart: true })).toMatchObject({ granted: false, action: 'restart' })
  })

  it('clicking is optional and says so', () => {
    const row = describeRow('accessibility', status())
    expect(row.optional).toBe(true)
    expect(row.action).toBe('request')
    expect(describeRow('microphone', status()).optional).toBe(false)
  })

  it('suggests a restart when screen access flipped to allowed during setup but capture is still empty', () => {
    expect(screenNeedsRestart('not-determined', status({ screen: 'granted', probe: 'empty' }))).toBe(true)
    expect(screenNeedsRestart('not-determined', status({ screen: 'granted', probe: 'ok' }))).toBe(false)
    expect(screenNeedsRestart('granted', status({ screen: 'granted', probe: 'ok' }))).toBe(false)
    expect(screenNeedsRestart(null, status({ screen: 'granted', needsRestart: true }))).toBe(true)
    expect(screenNeedsRestart('denied', null)).toBe(false)
  })
})
