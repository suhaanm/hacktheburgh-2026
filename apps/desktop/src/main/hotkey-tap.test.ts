import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => {
  const handlers = new Map<string, () => void>()
  return {
    handlers,
    register: vi.fn((a: string, fn: () => void) => {
      if (handlers.has(a)) return false
      handlers.set(a, fn)
      return true
    }),
    unregister: vi.fn((a: string) => void handlers.delete(a)),
  }
})
vi.mock('electron', () => ({ globalShortcut: { register: mocks.register, unregister: mocks.unregister, isRegistered: (a: string) => mocks.handlers.has(a) } }))

import { Bus } from './bus'
import { TALK_RELEASE_MS, registerHotkeys } from './hotkey'
import { SettingsStore } from './settings'

beforeEach(() => {
  mocks.handlers.clear()
  vi.spyOn(console, 'log').mockImplementation(() => undefined)
})

function rig() {
  const timers: { fn: () => void; ms: number }[] = []
  const events: string[] = []
  const bus = new Bus()
  bus.on('talk', (e) => void events.push(`${e.phase}`))
  const askTap = vi.fn()
  registerHotkeys(bus, new SettingsStore(null), { askTap, raisePanel: () => events.push('raise'), setTimer: (fn, ms) => (timers.push({ fn, ms }), timers.length), clearTimer: () => undefined })
  const key = () => mocks.handlers.get('Alt+Space')!()
  const letGo = () => timers.at(-1)!.fn()
  return { key, letGo, events, askTap, timers }
}

describe('Option-Space: tap opens Ask, hold talks', () => {
  it('a tap (the handler runs once, the keyboard never repeats it) is released after the pause and opens the Ask surface', () => {
    const r = rig()
    r.key()
    expect(r.timers.at(-1)!.ms).toBe(TALK_RELEASE_MS)
    r.letGo()
    expect(r.events).toEqual(['raise', 'press', 'release'])
    expect(r.askTap).toHaveBeenCalledTimes(1)
  })
  it('a hold (the key repeats) talks as before and does not open the Ask surface', () => {
    const r = rig()
    r.key()
    r.key()
    r.key()
    r.letGo()
    expect(r.events).toEqual(['raise', 'press', 'release'])
    expect(r.askTap).not.toHaveBeenCalled()
  })
  it('the next press starts again: tap, hold, tap', () => {
    const r = rig()
    r.key()
    r.letGo()
    r.key()
    r.key()
    r.letGo()
    r.key()
    r.letGo()
    expect(r.askTap).toHaveBeenCalledTimes(2)
  })
})
