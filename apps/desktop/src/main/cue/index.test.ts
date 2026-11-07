import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// Electron is not needed to test the wiring: the shortcuts, the screen and the windows are stand-ins, and the panel window is switched off.
const shortcuts = vi.hoisted(() => ({ register: vi.fn(() => true), unregister: vi.fn(), isRegistered: vi.fn(() => false) }))
vi.mock('electron', () => ({
  globalShortcut: shortcuts,
  screen: { getCursorScreenPoint: () => ({ x: 10, y: 10 }), getPrimaryDisplay: () => ({ bounds: { x: 0, y: 0, width: 1440, height: 900 }, workArea: { x: 0, y: 25, width: 1440, height: 800 } }) },
  ipcMain: { handle: vi.fn(), on: vi.fn(), removeHandler: vi.fn(), removeAllListeners: vi.fn() },
  BrowserWindow: class {
    constructor() {
      throw new Error('a window must not be created in this test')
    }
  },
}))

import { Bus } from '../bus'
import { setKilled } from '../kill-flag'
import type { CueStartContext } from './index'
import { cueEnabledByFlag, quietCueFor, startCue, stopCue } from './index'
import { FIXTURES } from './fixtures'
import { createFakeEngine } from './source'

function ctxWith(settings: Record<string, unknown>, engine = createFakeEngine()): { ctx: CueStartContext; engine: ReturnType<typeof createFakeEngine>; bus: Bus; overlay: Array<string> } {
  const bus = new Bus()
  const overlay: string[] = []
  const ctx = {
    state: {} as never,
    bus,
    settings: { get: () => settings, onChange: () => () => undefined } as never,
    userDataDir: null,
    sendOverlay: () => undefined,
    sendDock: () => undefined,
    log: () => undefined,
    overlay: { show: () => overlay.push('show'), clear: () => overlay.push('clear') },
    engine,
  } as unknown as CueStartContext
  return { ctx, engine, bus, overlay }
}

beforeEach(() => {
  vi.useFakeTimers({ now: 1_000_000 })
  process.env.ALONGSIDE_HEADLESS = '1' // no panel window
  delete process.env.UNDERSTUDY_X_CUE
  delete process.env.UNDERSTUDY_VOICE
})
afterEach(() => {
  stopCue()
  setKilled(false)
  vi.useRealTimers()
  delete process.env.ALONGSIDE_HEADLESS
  delete process.env.UNDERSTUDY_X_CUE
})

describe('startCue and stopCue', () => {
  it('flag off (the default): nothing is created and nothing is asked of anyone', async () => {
    const { ctx, engine } = ctxWith({ cueEnabled: true })
    expect(cueEnabledByFlag({})).toBe(false)
    expect(startCue(ctx)).toBeNull()
    await vi.advanceTimersByTimeAsync(10_000)
    expect(engine.polls).toHaveLength(0)
    expect(shortcuts.register).not.toHaveBeenCalled()
  })

  it('flag on but the worker has not switched Cue on: it runs, and asks the engine nothing', async () => {
    process.env.UNDERSTUDY_X_CUE = '1'
    const { ctx, engine } = ctxWith({})
    expect(startCue(ctx)).not.toBeNull()
    await vi.advanceTimersByTimeAsync(10_000)
    expect(engine.polls).toHaveLength(0)
  })

  it('flag on and switched on: it polls, shows the cue through the overlay, and stopCue stops everything', async () => {
    process.env.UNDERSTUDY_X_CUE = '1'
    const { ctx, engine, overlay } = ctxWith({ cueEnabled: true }, createFakeEngine([FIXTURES['cue-t2-l2']]))
    const h = startCue(ctx)!
    await vi.advanceTimersByTimeAsync(1_600)
    expect(engine.polls.length).toBeGreaterThan(0)
    expect(overlay).toContain('show')
    expect(h.controller.visible()?.kind).toBe('cue')
    expect(startCue(ctx)).toBe(h) // a second start is the same Cue
    stopCue()
    const polls = engine.polls.length
    await vi.advanceTimersByTimeAsync(10_000)
    expect(engine.polls.length).toBe(polls)
  })

  it('the kill switch stops it: no more polls, what is up comes down', async () => {
    process.env.UNDERSTUDY_X_CUE = '1'
    const { ctx, engine } = ctxWith({ cueEnabled: true }, createFakeEngine([FIXTURES['cue-t2-l2']]))
    const h = startCue(ctx)!
    await vi.advanceTimersByTimeAsync(1_600)
    setKilled(true)
    ctx.bus.emit('session:ended', { reason: 'stop' })
    expect(h.controller.visible()).toBeNull()
    const polls = engine.polls.length
    await vi.advanceTimersByTimeAsync(10_000)
    expect(engine.polls.length).toBe(polls)
  })

  it('quiet for an hour (the tray entry) takes the cue down and keeps it quiet', async () => {
    process.env.UNDERSTUDY_X_CUE = '1'
    const { ctx } = ctxWith({ cueEnabled: true }, createFakeEngine([FIXTURES['cue-t2-l2'], { ...(FIXTURES['cue-t2-l1'] as object), episode_id: 'ep-9' }]))
    const h = startCue(ctx)!
    await vi.advanceTimersByTimeAsync(1_600)
    expect(h.controller.visible()).not.toBeNull()
    quietCueFor(3_600_000)
    expect(h.controller.visible()).toBeNull()
    await vi.advanceTimersByTimeAsync(5_000)
    expect(h.controller.visible()).toBeNull()
  })

  it('Cue never watches the screen itself: it listens to the capture watcher\'s event, and a big change drops a ring', async () => {
    process.env.UNDERSTUDY_X_CUE = '1'
    const { ctx, bus } = ctxWith({ cueEnabled: true }, createFakeEngine([FIXTURES['cue-t2-l2']]))
    const h = startCue(ctx)!
    await vi.advanceTimersByTimeAsync(1_600)
    bus.emit('screen:changed', { score: 0.3 })
    await vi.advanceTimersByTimeAsync(1_300)
    expect(h.controller.visible()).toBeNull()
  })

  it('nothing speaks and no microphone opens by default, even with voice objects provided', async () => {
    process.env.UNDERSTUDY_X_CUE = '1'
    const said: string[] = []
    let listened = 0
    const { ctx } = ctxWith({ cueEnabled: true }, createFakeEngine([FIXTURES['cue-t4']]))
    ctx.speaker = { say: (id) => void said.push(id) }
    ctx.voice = { listenOnce: async () => (listened++, null) }
    ctx.workerUsedVoice = () => true
    startCue(ctx)
    await vi.advanceTimersByTimeAsync(1_600)
    expect(said).toEqual([])
    expect(listened).toBe(0)
  })
})
