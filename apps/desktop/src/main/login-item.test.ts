import { describe, expect, it, vi } from 'vitest'

vi.mock('electron', () => ({ app: { isPackaged: false, getLoginItemSettings: () => ({ openAtLogin: false }), setLoginItemSettings: vi.fn() } }))

import { SettingsStore } from './settings'
import { applyLoginItem, registerLoginItem } from './login-item'

const deps = (over: Partial<Parameters<typeof applyLoginItem>[1]> = {}) => {
  const set = vi.fn()
  const log = vi.fn()
  return { set, log, d: { platform: 'darwin' as const, isPackaged: true, getOpenAtLogin: () => false, setOpenAtLogin: set, log, ...over } }
}

describe('applyLoginItem', () => {
  it('registers a packaged macOS build', () => {
    const { d, set } = deps()
    expect(applyLoginItem(true, d)).toBe('applied')
    expect(set).toHaveBeenCalledWith(true)
  })

  it('does nothing when the state already matches', () => {
    const { d, set } = deps({ getOpenAtLogin: () => true })
    expect(applyLoginItem(true, d)).toBe('unchanged')
    expect(set).not.toHaveBeenCalled()
  })

  it('removes it when turned off', () => {
    const { d, set } = deps({ getOpenAtLogin: () => true })
    expect(applyLoginItem(false, d)).toBe('applied')
    expect(set).toHaveBeenCalledWith(false)
  })

  it('is a no-op with a clear log line in a dev build', () => {
    const { d, set, log } = deps({ isPackaged: false })
    expect(applyLoginItem(true, d)).toBe('skipped-dev')
    expect(set).not.toHaveBeenCalled()
    expect(log.mock.calls[0][0]).toContain('development build')
  })

  it('stays quiet in a dev build when the setting is off', () => {
    const { d, log } = deps({ isPackaged: false })
    applyLoginItem(false, d)
    expect(log).not.toHaveBeenCalled()
  })

  it('is a no-op off macOS', () => {
    const { d, set } = deps({ platform: 'linux' })
    expect(applyLoginItem(true, d)).toBe('skipped-platform')
    expect(set).not.toHaveBeenCalled()
  })
})

describe('registerLoginItem', () => {
  it('applies at startup and on change of launchAtLogin only', () => {
    const settings = new SettingsStore(null)
    settings.patch({ launchAtLogin: true })
    let current = false
    const set = vi.fn((open: boolean) => {
      current = open
    })
    const off = registerLoginItem(settings, { platform: 'darwin', isPackaged: true, getOpenAtLogin: () => current, setOpenAtLogin: set, log: () => undefined })
    expect(set).toHaveBeenLastCalledWith(true)
    settings.patch({ captions: false })
    expect(set).toHaveBeenCalledTimes(1)
    settings.patch({ launchAtLogin: false })
    expect(set).toHaveBeenLastCalledWith(false)
    off()
    settings.patch({ launchAtLogin: true })
    expect(set).toHaveBeenCalledTimes(2)
  })
})
