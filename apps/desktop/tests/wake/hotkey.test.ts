import { beforeEach, describe, expect, it, vi } from 'vitest'

const handlers = new Map<string, () => void>()
let taken = new Set<string>()
vi.mock('electron', () => ({
  globalShortcut: {
    register: vi.fn((acc: string, cb: () => void) => {
      if (taken.has(acc)) return false
      handlers.set(acc, cb)
      return true
    }),
    unregister: vi.fn((acc: string) => handlers.delete(acc)),
  },
}))

import { Bus } from '../../src/main/bus'
import { registerHotkeys, PANEL_ACCELERATORS, START_ACCELERATORS, STOP_ACCELERATORS } from '../../src/main/hotkey'
import { StateStore } from '../../src/main/state'
import { registerSession } from '../../src/main/session'
import { IPC } from '../../src/shared/ipc'
import { DEFAULT_SETTINGS } from '../../src/shared/settings'

const settingsStub = (persona: 'marcus' | 'amelia' | null) => ({ get: () => ({ ...DEFAULT_SETTINGS, persona }) }) as never

beforeEach(() => {
  handlers.clear()
  taken = new Set()
})

describe('global hotkeys', () => {
  it('registers every start and stop accelerator and unregisters them on quit', () => {
    const off = registerHotkeys(new Bus(), settingsStub(null))
    for (const a of [...START_ACCELERATORS, ...STOP_ACCELERATORS]) expect(handlers.has(a)).toBe(true)
    off()
    expect(handlers.size).toBe(0)
  })

  it('start emits session:request with the last persona and source hotkey; falls back to the default persona', () => {
    const bus = new Bus()
    const seen: unknown[] = []
    bus.on('session:request', (r) => seen.push(r))
    registerHotkeys(bus, settingsStub('amelia'))
    handlers.get(START_ACCELERATORS[0])!()
    registerHotkeys(bus, settingsStub(null))
    handlers.get(START_ACCELERATORS[0])!()
    expect(seen).toEqual([
      { personaId: 'amelia', source: 'hotkey' },
      { personaId: 'marcus', source: 'hotkey' },
    ])
  })

  it('start is ignored while a session is already running (no accidental restart)', () => {
    const bus = new Bus()
    const state = new StateStore(DEFAULT_SETTINGS)
    const seen: unknown[] = []
    bus.on('session:request', (r) => seen.push(r))
    registerHotkeys(bus, settingsStub(null), { state })
    state.patch({ phase: 'live' })
    handlers.get(START_ACCELERATORS[0])!()
    state.patch({ phase: 'listening_for_name' })
    handlers.get(START_ACCELERATORS[0])!()
    expect(seen).toHaveLength(1)
  })

  it('stop closes the session through the injected stop, or via the bus when none is given', () => {
    const stop = vi.fn()
    registerHotkeys(new Bus(), settingsStub(null), { stop })
    handlers.get(STOP_ACCELERATORS[0])!()
    expect(stop).toHaveBeenCalledWith('stop')

    handlers.clear()
    const bus = new Bus()
    const ended: unknown[] = []
    bus.on('session:ended', (e) => ended.push(e))
    registerHotkeys(bus, settingsStub(null))
    handlers.get(STOP_ACCELERATORS[1])!()
    expect(ended).toEqual([{ reason: 'stop' }])
  })

  it('tolerates a taken combo by using the next fallback and stays silent in state', () => {
    taken = new Set([START_ACCELERATORS[0]])
    const state = new StateStore(DEFAULT_SETTINGS)
    registerHotkeys(new Bus(), settingsStub(null), { state })
    expect(handlers.has(START_ACCELERATORS[0])).toBe(false)
    expect(handlers.has(START_ACCELERATORS[1])).toBe(true)
    expect(state.get().lastError).toBeUndefined()
  })

  it('surfaces a visible error in state when no start shortcut could be registered', () => {
    taken = new Set(START_ACCELERATORS)
    const state = new StateStore(DEFAULT_SETTINGS)
    registerHotkeys(new Bus(), settingsStub(null), { state })
    expect(state.get().lastError).toMatch(/starting is taken/i)
  })
})

describe('Stop hotkey against the real session controller', () => {
  it('tells the dock to close Live and returns the state to its resting phase', () => {
    const bus = new Bus()
    const state = new StateStore(DEFAULT_SETTINGS)
    const sendDock = vi.fn()
    const settings = { get: () => ({ ...DEFAULT_SETTINGS }), patch: vi.fn(), onChange: vi.fn() }
    const ctx = { bus, state, settings, sendDock, sendOverlay: vi.fn(), userDataDir: '', log: vi.fn() }
    const services = { runner: { abort: vi.fn() }, overlay: { clear: vi.fn(), chip: vi.fn() } }
    const session = registerSession(ctx as never, services as never, { cancel: vi.fn() } as never)
    registerHotkeys(bus, settings as never, { state, stop: (r) => session.stop(r) })

    handlers.get(START_ACCELERATORS[0])!() // Start: dock is told to open the session
    expect(sendDock).toHaveBeenCalledWith(IPC.sessionStart, { personaId: 'marcus', source: 'hotkey' })
    expect(state.get().phase).toBe('connecting')

    handlers.get(STOP_ACCELERATORS[0])!() // Stop
    expect(sendDock).toHaveBeenCalledWith(IPC.sessionStop, 'stop')
    expect(state.get().phase).toBe('listening_for_name')
    expect(services.runner.abort).toHaveBeenCalled()
  })

  it('registers the panel shortcut only when a toggle is supplied, and it calls it', () => {
    registerHotkeys(new Bus(), settingsStub(null))
    expect(handlers.has(PANEL_ACCELERATORS[0])).toBe(false)
    const togglePanel = vi.fn()
    registerHotkeys(new Bus(), settingsStub(null), { togglePanel })
    expect(PANEL_ACCELERATORS[0]).toBe('CommandOrControl+Alt+P')
    for (const a of PANEL_ACCELERATORS) expect(handlers.has(a)).toBe(true)
    handlers.get(PANEL_ACCELERATORS[0])!()
    expect(togglePanel).toHaveBeenCalledTimes(1)
  })

  it('tolerates the panel combos being taken: no throw, no error banner, the others still work', () => {
    taken = new Set(PANEL_ACCELERATORS)
    const state = new StateStore(DEFAULT_SETTINGS)
    const off = registerHotkeys(new Bus(), settingsStub(null), { state, togglePanel: vi.fn() })
    expect(state.get().lastError).toBeUndefined()
    expect(handlers.has(START_ACCELERATORS[0])).toBe(true)
    off()
  })
})
