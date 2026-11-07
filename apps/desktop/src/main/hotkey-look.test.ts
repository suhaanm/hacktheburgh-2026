import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => {
  const handlers = new Map<string, () => void>()
  const taken = new Set<string>()
  return {
    handlers,
    taken,
    register: vi.fn((a: string, fn: () => void) => {
      if (taken.has(a) || handlers.has(a)) return false
      handlers.set(a, fn)
      return true
    }),
    unregister: vi.fn((a: string) => void handlers.delete(a)),
  }
})
vi.mock('electron', () => ({ globalShortcut: { register: mocks.register, unregister: mocks.unregister, isRegistered: (a: string) => mocks.handlers.has(a) } }))

import { Bus } from './bus'
import { lastHotkeyReport, LOOK_ACCELERATORS, registerHotkeys } from './hotkey'
import { SettingsStore } from './settings'

beforeEach(() => {
  mocks.handlers.clear()
  mocks.taken.clear()
  mocks.register.mockClear()
  vi.spyOn(console, 'log').mockImplementation(() => undefined)
})

describe('look-now hotkey', () => {
  it('binds Option+Shift+Space and calls the look handler; one key only', () => {
    const look = vi.fn()
    registerHotkeys(new Bus(), new SettingsStore(null), { look })
    expect(lastHotkeyReport()?.look).toEqual(['Alt+Shift+Space'])
    mocks.handlers.get('Alt+Shift+Space')!()
    expect(look).toHaveBeenCalledTimes(1)
    expect(LOOK_ACCELERATORS.filter((a) => mocks.handlers.has(a))).toEqual(['Alt+Shift+Space'])
  })

  it('falls back when another app owns the first key, and registers nothing when every one is taken', () => {
    mocks.taken.add('Alt+Shift+Space')
    registerHotkeys(new Bus(), new SettingsStore(null), { look: () => undefined })
    expect(lastHotkeyReport()?.look).toEqual(['CommandOrControl+Alt+Shift+L'])
    mocks.handlers.clear()
    for (const a of LOOK_ACCELERATORS) mocks.taken.add(a)
    registerHotkeys(new Bus(), new SettingsStore(null), { look: () => undefined })
    expect(lastHotkeyReport()?.look).toEqual([])
  })

  it('does not take the key the worker chose for the talk key', () => {
    const s = new SettingsStore(null)
    s.patch({ talkHotkey: 'Alt+Shift+Space' }, { trusted: true })
    registerHotkeys(new Bus(), s, { look: () => undefined })
    expect(lastHotkeyReport()?.talk).toEqual(['Alt+Shift+Space'])
    expect(lastHotkeyReport()?.look).toEqual(['CommandOrControl+Alt+Shift+L'])
  })

  it('is not registered without the awareness layer, and unregisters on dispose', () => {
    const off = registerHotkeys(new Bus(), new SettingsStore(null), {})
    expect(lastHotkeyReport()?.look).toEqual([])
    off()
    const off2 = registerHotkeys(new Bus(), new SettingsStore(null), { look: () => undefined })
    expect(mocks.handlers.has('Alt+Shift+Space')).toBe(true)
    off2()
    expect(mocks.handlers.has('Alt+Shift+Space')).toBe(false)
  })
})
