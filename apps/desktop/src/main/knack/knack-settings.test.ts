import { describe, expect, it } from 'vitest'
import { DEFAULT_SETTINGS, coerceSettings } from '../../shared/settings'
import { SettingsStore } from '../settings'
import { applyShowInDock, registerDock } from './dock'

describe('the Knack settings', () => {
  it('default to a Dock icon, minimising while a run works, and live models', () => {
    expect(DEFAULT_SETTINGS).toMatchObject({ showInDock: true, moveAsideWhileWorking: true, useLiveModels: true })
    expect(coerceSettings({ onboardingDone: true })).toMatchObject({ showInDock: true, moveAsideWhileWorking: true, useLiveModels: true }) // an older file without the keys
    expect(coerceSettings({ showInDock: false, moveAsideWhileWorking: false, useLiveModels: false })).toMatchObject({ showInDock: false, moveAsideWhileWorking: false, useLiveModels: false })
  })
  it('live models can only be switched from the Settings UI: it costs money, so main drops it from every other source', () => {
    const s = new SettingsStore(null)
    s.patch({ useLiveModels: false })
    expect(s.get().useLiveModels).toBe(true)
    s.patch({ useLiveModels: false, showInDock: false })
    expect(s.get()).toMatchObject({ useLiveModels: true, showInDock: false })
    s.patch({ useLiveModels: false }, { trusted: true })
    expect(s.get().useLiveModels).toBe(false)
  })
})

describe('the Dock icon', () => {
  const fake = () => {
    const calls: string[] = []
    return { calls, dock: { show: () => void calls.push('show'), hide: () => void calls.push('hide') } }
  }
  it('is shown or hidden on macOS and skipped elsewhere or without a Dock', () => {
    const f = fake()
    expect(applyShowInDock(true, { platform: 'darwin', dock: f.dock })).toBe('shown')
    expect(applyShowInDock(false, { platform: 'darwin', dock: f.dock })).toBe('hidden')
    expect(f.calls).toEqual(['show', 'hide'])
    expect(applyShowInDock(true, { platform: 'linux', dock: f.dock })).toBe('skipped')
    expect(applyShowInDock(true, { platform: 'darwin' })).toBe('skipped')
  })
  it('follows the setting at start and when it changes, and a hidden run never shows an icon', () => {
    const f = fake()
    const settings = new SettingsStore(null)
    const off = registerDock(settings, { platform: 'darwin', dock: f.dock })
    expect(f.calls).toEqual(['show'])
    settings.patch({ showInDock: false })
    settings.patch({ moveAsideWhileWorking: false }) // unrelated: nothing happens
    settings.patch({ showInDock: true })
    expect(f.calls).toEqual(['show', 'hide', 'show'])
    off()
    settings.patch({ showInDock: false })
    expect(f.calls).toHaveLength(3)
    const h = fake()
    registerDock(new SettingsStore(null), { platform: 'darwin', dock: h.dock, hidden: true })
    expect(h.calls).toEqual(['hide'])
  })
  it('a Dock that throws is skipped, not fatal', () => {
    expect(applyShowInDock(true, { platform: 'darwin', dock: { show: () => { throw new Error('no dock') }, hide: () => undefined } })).toBe('skipped')
  })
})
