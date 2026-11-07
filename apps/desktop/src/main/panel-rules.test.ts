import { describe, expect, it } from 'vitest'
import { coerceSettings, DEFAULT_SETTINGS } from '../shared/settings'
import { shouldShowDockAtStart, trayStateKind } from './panel-rules'

describe('startup visibility', () => {
  const s = { showDock: false, onboardingDone: true, showMenuBarIcon: true }
  it('is hidden by default once setup is done', () => {
    expect(shouldShowDockAtStart(s)).toBe(false)
  })
  it('shows when the user keeps it open', () => {
    expect(shouldShowDockAtStart({ ...s, showDock: true })).toBe(true)
  })
  it('shows on first run so setup is visible', () => {
    expect(shouldShowDockAtStart({ ...s, onboardingDone: false })).toBe(true)
  })
  it('shows when there is no menu bar item to bring it back', () => {
    expect(shouldShowDockAtStart({ ...s, showMenuBarIcon: false })).toBe(true)
  })
  it('never shows headless', () => {
    expect(shouldShowDockAtStart({ ...s, showDock: true }, true)).toBe(false)
  })
})

describe('showDock setting', () => {
  it('defaults to false', () => {
    expect(DEFAULT_SETTINGS.showDock).toBe(false)
  })
  it('an older saved profile without the key reads as false; a saved true is kept', () => {
    expect(coerceSettings({ onboardingDone: true, persona: 'marcus' }).showDock).toBe(false)
    expect(coerceSettings({ onboardingDone: true, showDock: true }).showDock).toBe(true)
    expect(coerceSettings({ showDock: 'yes' }).showDock).toBe(false)
  })
})

describe('trayStateKind priority', () => {
  it('error beats mute beats working beats the phase', () => {
    expect(trayStateKind({ phase: 'error', micMuted: true, agents: [{ status: 'running' }] })).toBe('error')
    expect(trayStateKind({ phase: 'live', micMuted: true, agents: [{ status: 'running' }] })).toBe('muted')
    expect(trayStateKind({ phase: 'live', micMuted: false, agents: [{ status: 'running' }] })).toBe('working')
    expect(trayStateKind({ phase: 'thinking', micMuted: false })).toBe('thinking')
  })
})
