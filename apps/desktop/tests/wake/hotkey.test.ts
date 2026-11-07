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
import { lastHotkeyReport, registerHotkeys, PANEL_ACCELERATORS, START_ACCELERATORS, STOP_ACCELERATORS } from '../../src/main/hotkey'
import { StateStore } from '../../src/main/state'
import { registerSession } from '../../src/main/session'
import { IPC } from '../../src/shared/ipc'
import { DEFAULT_SETTINGS } from '../../src/shared/settings'

const settingsStub = (persona: import('../../src/shared/protocol').PersonaId | null) => ({ get: () => ({ ...DEFAULT_SETTINGS, persona }) }) as never

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
      { personaId: 'understudy', source: 'hotkey' },
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
    const state = new StateStore({ ...DEFAULT_SETTINGS, wakeEnabled: true })
    const sendDock = vi.fn()
    const settings = { get: () => ({ ...DEFAULT_SETTINGS, wakeEnabled: true }), patch: vi.fn(), onChange: vi.fn() }
    const ctx = { bus, state, settings, sendDock, sendOverlay: vi.fn(), userDataDir: '', log: vi.fn() }
    const services = { runner: { abort: vi.fn() }, overlay: { clear: vi.fn(), chip: vi.fn() } }
    const session = registerSession(ctx as never, services as never, { cancel: vi.fn() } as never)
    registerHotkeys(bus, settings as never, { state, stop: (r) => session.stop(r) })

    handlers.get(START_ACCELERATORS[0])!() // Start: dock is told to open the session
    expect(sendDock).toHaveBeenCalledWith(IPC.sessionStart, { personaId: 'understudy', source: 'hotkey' })
    expect(state.get().phase).toBe('connecting')

    handlers.get(STOP_ACCELERATORS[0])!() // Stop
    expect(sendDock).toHaveBeenCalledWith(IPC.sessionStop, 'stop')
    expect(state.get().phase).toBe('listening_for_name') // the name listener is on only because this test turned it on
    expect(services.runner.abort).toHaveBeenCalled()
  })

  it('the microphone is not listening by default: the name listener is off, so the resting phase is asleep', () => {
    expect(DEFAULT_SETTINGS.wakeEnabled).toBe(false)
    const state = new StateStore(DEFAULT_SETTINGS)
    const settings = { get: () => ({ ...DEFAULT_SETTINGS }), patch: vi.fn(), onChange: vi.fn() }
    const ctx = { bus: new Bus(), state, settings, sendDock: vi.fn(), sendOverlay: vi.fn(), userDataDir: '', log: vi.fn() }
    const session = registerSession(ctx as never, { runner: { abort: vi.fn() }, overlay: { clear: vi.fn(), chip: vi.fn() } } as never, { cancel: vi.fn() } as never)
    session.stop('stop')
    expect(state.get().phase).toBe('asleep')
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

describe('the talk key (hold to talk; the panel comes up, `talk` is emitted)', () => {
  const timers: Array<{ fn: () => void; ms: number; live: boolean }> = []
  const fake = { setTimer: (fn: () => void, ms: number) => (timers.push({ fn, ms, live: true }), timers.length - 1), clearTimer: (h: unknown) => void (timers[h as number]!.live = false) }
  const fire = (): void => {
    const t = [...timers].reverse().find((x) => x.live)
    if (t) {
      t.live = false
      t.fn()
    }
  }
  beforeEach(() => (timers.length = 0))

  it('is Option+Space by default and registers it', () => {
    registerHotkeys(new Bus(), settingsStub(null), fake)
    expect(DEFAULT_SETTINGS.talkHotkey).toBe('Alt+Space')
    expect(handlers.has('Alt+Space')).toBe(true)
  })

  it('press raises the panel and emits talk once however often the keyboard repeats; it releases when the repeats stop', () => {
    const bus = new Bus()
    const seen: string[] = []
    bus.on('talk', (e) => seen.push(`${e.source}:${e.phase}`))
    const raised: number[] = []
    registerHotkeys(bus, settingsStub(null), { ...fake, raisePanel: () => void raised.push(1) })
    const press = handlers.get('Alt+Space')!
    press()
    press()
    press()
    expect(seen).toEqual(['hotkey:press'])
    expect(raised).toHaveLength(1)
    fire() // no repeat for the release time: the key is up
    expect(seen).toEqual(['hotkey:press', 'hotkey:release'])
    press() // a later press is a new press
    expect(seen.at(-1)).toBe('hotkey:press')
    expect(raised).toHaveLength(2)
  })

  it('falls back when another app owns the chosen combo, and follows a changed setting', () => {
    taken = new Set(['Alt+Space'])
    registerHotkeys(new Bus(), settingsStub(null), fake)
    expect(handlers.has('Alt+Space')).toBe(false)
    expect(handlers.has('Alt+Shift+Space')).toBe(true)
    handlers.clear()
    taken = new Set()
    let listener: ((s: unknown, p: Record<string, unknown>) => void) | null = null
    let hot = 'Alt+Space'
    const store = { get: () => ({ ...DEFAULT_SETTINGS, talkHotkey: hot }), onChange: (l: typeof listener) => ((listener = l), () => undefined) } as never
    registerHotkeys(new Bus(), store, fake)
    expect(handlers.has('Alt+Space')).toBe(true)
    hot = 'Control+Alt+T'
    listener!({}, { talkHotkey: hot })
    expect(handlers.has('Control+Alt+T')).toBe(true)
    expect(handlers.has('Alt+Space')).toBe(false)
  })
})

describe('hotkey registration report (the pre-R1 checklist: the kill hotkey must be bound)', () => {
  it('says whether the kill hotkey and the talk key registered, and which combos failed', () => {
    registerHotkeys(new Bus(), settingsStub(null), { kill: () => undefined })
    expect(lastHotkeyReport()).toMatchObject({ killRegistered: true, talkRegistered: true })
    expect(lastHotkeyReport()!.kill.length).toBeGreaterThan(0)
    handlers.clear()
    taken = new Set(['CommandOrControl+Alt+Shift+K', 'CommandOrControl+Alt+Shift+Backspace', 'CommandOrControl+Alt+Shift+.'])
    registerHotkeys(new Bus(), settingsStub(null), { kill: () => undefined })
    expect(lastHotkeyReport()).toMatchObject({ killRegistered: false, kill: [] })
    expect(lastHotkeyReport()!.failed).toContain('CommandOrControl+Alt+Shift+K')
  })
})
