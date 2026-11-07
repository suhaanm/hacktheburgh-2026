import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { IPC } from '../shared/ipc'
import { DEFAULT_SETTINGS } from '../shared/settings'
import { CONFIRM_TIMEOUT_MS, ConfirmBroker } from './confirm'
import { SettingsStore } from './settings'
import { StateStore } from './state'
import { NOTIFICATION_TITLE, TOAST_MARGIN, TOAST_WIDTH, registerToast } from './toast'

// A minimal Electron: windows and notifications are recorded so the tests can look at what main asked for.
vi.mock('electron', async () => {
  const { EventEmitter } = await import('node:events')
  const fake = {
    windows: [] as FakeWindow[],
    notifications: [] as FakeNotification[],
    throwOnCreate: false,
    notificationsSupported: true,
    nextId: 100,
  }
  class FakeWebContents extends EventEmitter {
    id = fake.nextId++
    destroyed = false
    sent: unknown[][] = []
    send = (...args: unknown[]) => void this.sent.push(args)
    isDestroyed = () => this.destroyed
    executeJavaScript = vi.fn(async () => 180)
    setWindowOpenHandler = vi.fn()
  }
  class FakeWindow extends EventEmitter {
    webContents = new FakeWebContents()
    destroyed = false
    visible = false
    options: Record<string, unknown>
    constructor(options: Record<string, unknown>) {
      super()
      if (fake.throwOnCreate) throw new Error('window creation failed')
      this.options = options
      fake.windows.push(this)
    }
    setAlwaysOnTop = vi.fn()
    setVisibleOnAllWorkspaces = vi.fn()
    setContentProtection = vi.fn()
    setBounds = vi.fn()
    loadURL = vi.fn(async () => undefined)
    loadFile = vi.fn(async () => undefined)
    showInactive = vi.fn(() => void (this.visible = true))
    show = vi.fn()
    moveTop = vi.fn()
    isVisible = () => this.visible
    isDestroyed = () => this.destroyed
    destroy = () => {
      this.destroyed = true
      this.webContents.destroyed = true
      this.emit('closed')
    }
  }
  class FakeNotification extends EventEmitter {
    static isSupported = () => fake.notificationsSupported
    shown = 0
    closed = 0
    constructor(public options: Record<string, unknown>) {
      super()
      fake.notifications.push(this)
    }
    show = () => void this.shown++
    close = () => void this.closed++
  }
  return {
    __fake: fake,
    BrowserWindow: FakeWindow,
    Notification: FakeNotification,
    screen: { getPrimaryDisplay: () => ({ workArea: { x: 0, y: 25, width: 1440, height: 875 } }) },
  }
})

interface FakeWebContents {
  id: number
  sent: unknown[][]
  emit(event: string, ...args: unknown[]): boolean
  executeJavaScript: ReturnType<typeof vi.fn>
}
interface FakeWindow {
  options: Record<string, unknown>
  webContents: FakeWebContents
  destroyed: boolean
  setAlwaysOnTop: ReturnType<typeof vi.fn>
  setVisibleOnAllWorkspaces: ReturnType<typeof vi.fn>
  setContentProtection: ReturnType<typeof vi.fn>
  setBounds: ReturnType<typeof vi.fn>
  showInactive: ReturnType<typeof vi.fn>
  moveTop: ReturnType<typeof vi.fn>
  emit(event: string): boolean
}
interface FakeNotification {
  options: Record<string, unknown>
  shown: number
  closed: number
  emit(event: string): boolean
}
const electron = (await import('electron')) as unknown as { __fake: { windows: FakeWindow[]; notifications: FakeNotification[]; throwOnCreate: boolean; notificationsSupported: boolean } }
const fake = electron.__fake

function setup(opts: { confirmStyle?: 'toast' | 'dock'; capturable?: boolean; disabled?: boolean; loadTimeoutMs?: number } = {}) {
  const settings = new SettingsStore(null)
  settings.patch({ confirmStyle: opts.confirmStyle ?? 'toast' }, { trusted: true })
  const state = new StateStore(settings.get())
  const log = vi.fn()
  const adopted: number[] = []
  const released: number[] = []
  const toast = registerToast({
    ctx: { state, settings, log },
    adoptOwner: (id) => {
      adopted.push(id)
      return () => void released.push(id)
    },
    disabled: opts.disabled ?? false,
    capturable: opts.capturable ?? false,
    loadTimeoutMs: opts.loadTimeoutMs,
  })
  const confirm = new ConfirmBroker(state)
  const loaded = (i = 0) => fake.windows[i]!.webContents.emit('did-finish-load')
  return { settings, state, log, adopted, released, toast, confirm, loaded }
}

const OPTIONS: [string, string] = ['Yes, open it', 'Not now']

beforeEach(() => {
  fake.windows.length = 0
  fake.notifications.length = 0
  fake.throwOnCreate = false
  fake.notificationsSupported = true
  vi.useFakeTimers()
  vi.stubEnv('ALONGSIDE_CONFIRM_STYLE', '')
  vi.stubEnv('ALONGSIDE_HEADLESS', '')
  vi.stubEnv('ALONGSIDE_NO_OVERLAY', '')
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllEnvs()
})

describe('registerToast: showing', () => {
  it('opens a protected, always-on-top, all-Spaces toast at the top right and shows it without taking focus', async () => {
    const { confirm, state, loaded, toast, adopted } = setup()
    expect(fake.windows).toHaveLength(0)
    const answer = confirm.ask('Open example.com for you?', OPTIONS)
    expect(fake.windows).toHaveLength(1)
    const win = fake.windows[0]!
    expect(win.options).toMatchObject({ frame: false, transparent: true, alwaysOnTop: true, skipTaskbar: true, show: false })
    expect(win.options.x).toBe(1440 - TOAST_WIDTH - TOAST_MARGIN)
    expect(win.options.y).toBe(25 + TOAST_MARGIN) // below the menu bar (workArea.y)
    expect(win.setContentProtection).toHaveBeenCalledWith(true)
    expect(win.setAlwaysOnTop).toHaveBeenCalledWith(true, 'screen-saver', 1)
    expect(win.setVisibleOnAllWorkspaces).toHaveBeenCalledWith(true, expect.objectContaining({ visibleOnFullScreen: true }))
    expect(adopted).toEqual([win.webContents.id])
    expect(win.showInactive).not.toHaveBeenCalled() // not before the page is ready
    expect(toast.visible()).toBe(false)

    loaded()
    expect(win.showInactive).toHaveBeenCalledTimes(1)
    expect(toast.visible()).toBe(true)
    const pushed = win.webContents.sent.find(([channel]) => channel === IPC.stateUpdate)
    expect(pushed?.[1]).toMatchObject({ pendingConfirm: { question: 'Open example.com for you?', options: OPTIONS }, captions: [], agents: [] })

    const mark = state.get().toastConfirm
    expect(mark?.id).toBe(state.get().pendingConfirm?.id)
    expect(mark?.expiresAt).toBe(Date.now() + CONFIRM_TIMEOUT_MS)
    confirm.cancel()
    expect(await answer).toBeNull()
  })

  it('fits the window height to the card the page reports', async () => {
    const { confirm, loaded } = setup()
    void confirm.ask('Q?', OPTIONS)
    fake.windows[0]!.webContents.executeJavaScript.mockResolvedValue(220)
    loaded()
    await vi.advanceTimersByTimeAsync(10)
    const last = fake.windows[0]!.setBounds.mock.calls.at(-1)![0] as { height: number; width: number }
    expect(last.width).toBe(TOAST_WIDTH)
    expect(last.height).toBe(220 + 2 * TOAST_MARGIN + 4)
  })

  it('turns content protection off only for demo recording (ALONGSIDE_OVERLAY_CAPTURABLE)', () => {
    const { confirm } = setup({ capturable: true })
    void confirm.ask('Q?', OPTIONS)
    expect(fake.windows[0]!.setContentProtection).toHaveBeenCalledWith(false)
  })

  it('fires one native notification (not silent, question as body, no screen content) when the toast appears', () => {
    const { confirm, loaded } = setup()
    void confirm.ask('Open example.com for you?', OPTIONS)
    expect(fake.notifications).toHaveLength(0)
    loaded()
    expect(fake.notifications).toHaveLength(1)
    const n = fake.notifications[0]!
    expect(n.options).toEqual({ title: NOTIFICATION_TITLE, body: 'Open example.com for you?', silent: false })
    expect(n.shown).toBe(1)
  })

  it('clicking the notification raises the toast; unsupported notifications are skipped quietly', () => {
    const a = setup()
    void a.confirm.ask('Q?', OPTIONS)
    a.loaded()
    fake.notifications[0]!.emit('click')
    expect(fake.windows[0]!.moveTop).toHaveBeenCalled()
    expect(fake.windows[0]!.showInactive).toHaveBeenCalledTimes(2)
    a.confirm.cancel()

    fake.notificationsSupported = false
    const b = setup()
    void b.confirm.ask('Q2?', OPTIONS)
    expect(() => b.loaded(fake.windows.length - 1)).not.toThrow()
    expect(fake.notifications).toHaveLength(1) // only the first one
  })
})

describe('registerToast: hiding', () => {
  it.each([
    ['an answer', (c: ConfirmBroker, id: string) => c.answer(id, OPTIONS[0])],
    ['Stop (the session ends the confirm as a decline)', (c: ConfirmBroker) => c.cancel()],
    ['the session ending', (c: ConfirmBroker) => c.cancel()],
  ])('is destroyed the moment the request is cleared by %s', async (_name, clear) => {
    const { confirm, state, toast, loaded, released } = setup()
    const answer = confirm.ask('Q?', OPTIONS)
    loaded()
    const win = fake.windows[0]!
    clear(confirm, state.get().pendingConfirm!.id)
    await answer
    expect(win.destroyed).toBe(true)
    expect(toast.visible()).toBe(false)
    expect(state.get().toastConfirm).toBeUndefined()
    expect(released).toEqual([win.webContents.id])
    expect(fake.notifications[0]!.closed).toBe(1)
  })

  it('is destroyed when the confirm manager times the request out', async () => {
    const { confirm, state, loaded } = setup()
    const answer = confirm.ask('Q?', OPTIONS)
    loaded()
    await vi.advanceTimersByTimeAsync(CONFIRM_TIMEOUT_MS - 1)
    expect(fake.windows[0]!.destroyed).toBe(false)
    await vi.advanceTimersByTimeAsync(2)
    expect(await answer).toBeNull()
    expect(fake.windows[0]!.destroyed).toBe(true)
    expect(state.get().pendingConfirm).toBeUndefined()
  })

  it('is destroyed when pendingConfirm is cleared by any other path', () => {
    const { confirm, state, loaded } = setup()
    void confirm.ask('Q?', OPTIONS)
    loaded()
    state.patch({ pendingConfirm: undefined })
    expect(fake.windows[0]!.destroyed).toBe(true)
  })

  it('a newer request replaces the old toast with exactly one new one', () => {
    const { confirm, loaded } = setup()
    void confirm.ask('First?', OPTIONS)
    loaded(0)
    void confirm.ask('Second?', OPTIONS) // ConfirmBroker.ask cancels the first as a decline
    expect(fake.windows).toHaveLength(2)
    expect(fake.windows[0]!.destroyed).toBe(true)
    expect(fake.windows[1]!.destroyed).toBe(false)
    loaded(1)
    expect(fake.notifications).toHaveLength(2)
  })

  it('dispose removes a visible toast and stops listening', () => {
    const { confirm, toast, loaded } = setup()
    void confirm.ask('Q?', OPTIONS)
    loaded()
    toast.dispose()
    expect(fake.windows[0]!.destroyed).toBe(true)
    void confirm.ask('Again?', OPTIONS)
    expect(fake.windows).toHaveLength(1)
  })
})

describe('registerToast: never twice', () => {
  it('unrelated state changes do not create another window or notification for the same request', () => {
    const { confirm, state, loaded } = setup()
    void confirm.ask('Q?', OPTIONS)
    loaded()
    state.patch({ micMuted: true })
    state.addCaption('assistant', 'hello', true)
    state.patch({ phase: 'live' })
    expect(fake.windows).toHaveLength(1)
    expect(fake.notifications).toHaveLength(1)
    expect(fake.windows[0]!.showInactive).toHaveBeenCalledTimes(1)
    loaded() // a reload of the page must not show or notify again
    expect(fake.windows[0]!.showInactive).toHaveBeenCalledTimes(1)
    expect(fake.notifications).toHaveLength(1)
  })

  it('a request that fell back to the dock is not retried on later state changes', () => {
    const { confirm, state } = setup()
    void confirm.ask('Q?', OPTIONS)
    fake.windows[0]!.webContents.emit('did-fail-load', {}, -6, 'FILE_NOT_FOUND')
    state.patch({ micMuted: true })
    state.patch({ phase: 'live' })
    expect(fake.windows).toHaveLength(1)
    expect(state.get().toastConfirm).toBeUndefined()
  })
})

describe('registerToast: when there is no toast', () => {
  it("settings.confirmStyle 'dock' behaves as before: no window, no notification, no marker", () => {
    const { confirm, state } = setup({ confirmStyle: 'dock' })
    void confirm.ask('Q?', OPTIONS)
    expect(fake.windows).toHaveLength(0)
    expect(fake.notifications).toHaveLength(0)
    expect(state.get().pendingConfirm).toBeDefined()
    expect(state.get().toastConfirm).toBeUndefined()
  })

  it('ALONGSIDE_CONFIRM_STYLE=dock overrides the setting (end-to-end tests that drive the dock modal)', () => {
    vi.stubEnv('ALONGSIDE_CONFIRM_STYLE', 'dock')
    const { confirm } = setup()
    void confirm.ask('Q?', OPTIONS)
    expect(fake.windows).toHaveLength(0)
  })

  it('headless and no-overlay runs get no window (flag or environment)', () => {
    const a = setup({ disabled: true })
    void a.confirm.ask('Q?', OPTIONS)
    expect(fake.windows).toHaveLength(0)
    expect(a.toast.visible()).toBe(false)
    expect(() => a.toast.dispose()).not.toThrow()

    vi.stubEnv('ALONGSIDE_HEADLESS', '1')
    const settings = new SettingsStore(null)
    const state = new StateStore(settings.get())
    registerToast({ ctx: { state, settings, log: vi.fn() } })
    void new ConfirmBroker(state).ask('Q?', OPTIONS)
    expect(fake.windows).toHaveLength(0)
  })

  it('switching the setting to dock while a toast is up removes it and leaves the request for the dock', () => {
    const { confirm, state, settings, loaded } = setup()
    void confirm.ask('Q?', OPTIONS)
    loaded()
    settings.patch({ confirmStyle: 'dock' }, { trusted: true })
    state.patch({ micMuted: true }) // any state change makes main look again
    expect(fake.windows[0]!.destroyed).toBe(true)
    expect(state.get().toastConfirm).toBeUndefined()
    expect(state.get().pendingConfirm).toBeDefined()
    expect(fake.windows).toHaveLength(1)
  })
})

describe('registerToast: a prompt is never lost', () => {
  it('falls back to the dock when the window cannot be created', () => {
    fake.throwOnCreate = true
    const { confirm, state, log } = setup()
    void confirm.ask('Q?', OPTIONS)
    expect(fake.windows).toHaveLength(0)
    expect(state.get().pendingConfirm).toBeDefined()
    expect(state.get().toastConfirm).toBeUndefined() // the dock modal opens
    expect(log).toHaveBeenCalledWith('toast', expect.stringContaining('dock shows the prompt'), expect.any(String))
  })

  it('falls back when the page fails to load, the renderer dies, or the page never loads', () => {
    const a = setup()
    void a.confirm.ask('A?', OPTIONS)
    expect(a.state.get().toastConfirm).toBeDefined()
    fake.windows[0]!.webContents.emit('render-process-gone', {}, { reason: 'crashed' })
    expect(a.state.get().toastConfirm).toBeUndefined()
    expect(fake.windows[0]!.destroyed).toBe(true)
    a.toast.dispose()

    const b = setup({ loadTimeoutMs: 1000 })
    void b.confirm.ask('B?', OPTIONS)
    expect(b.state.get().toastConfirm).toBeDefined()
    vi.advanceTimersByTime(1001)
    expect(b.state.get().toastConfirm).toBeUndefined()
    expect(fake.windows[1]!.destroyed).toBe(true)
    expect(b.state.get().pendingConfirm).toBeDefined()
  })

  it('falls back if the window is closed from outside while the request is still pending', () => {
    const { confirm, state, loaded } = setup()
    void confirm.ask('Q?', OPTIONS)
    loaded()
    fake.windows[0]!.emit('closed')
    expect(state.get().toastConfirm).toBeUndefined()
    expect(state.get().pendingConfirm).toBeDefined()
  })
})

describe('settings', () => {
  it("defaults confirmStyle to 'toast'", () => {
    expect(DEFAULT_SETTINGS.confirmStyle).toBe('toast')
  })
})
