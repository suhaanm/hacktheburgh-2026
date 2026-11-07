// NOTIFY: permission prompts (ConfirmRequest in state.pendingConfirm) as a macOS-style toast at the top-right of the screen,
// plus one native notification. The toast is a separate small window; it only DISPLAYS the request. An approval can still only
// arrive as a real click (IPC confirm:answer, validated against the request id and its two options by ConfirmBroker).
import path from 'node:path'
import { BrowserWindow, Notification, screen } from 'electron'
import { IPC } from '../shared/ipc'
import type { CompanionState, ConfirmRequest } from '../shared/protocol'
import { CONFIRM_TIMEOUT_MS } from './confirm'
import type { ServiceContext } from './context'

export const TOAST_WIDTH = 400
export const TOAST_MARGIN = 12
const MIN_HEIGHT = 140
const MAX_HEIGHT = 560
const LOAD_TIMEOUT_MS = 4000
export const NOTIFICATION_TITLE = 'Alongside needs your OK'

export interface ToastDeps {
  ctx: Pick<ServiceContext, 'state' | 'settings' | 'log'>
  // windows.ts adoptOwner: lets the toast's webContents use the IPC the dock uses (answer a confirm). Optional in tests.
  adoptOwner?: (webContentsId: number) => () => void
  // No window at all (ALONGSIDE_HEADLESS / ALONGSIDE_NO_OVERLAY). Default: read from process.env.
  disabled?: boolean
  // ALONGSIDE_OVERLAY_CAPTURABLE=1 (demo recording) turns content protection off, exactly like the overlay.
  capturable?: boolean
  confirmTimeoutMs?: number
  loadTimeoutMs?: number
}

export interface ToastHandle {
  visible(): boolean
  dispose(): void
}

const NOOP: ToastHandle = { visible: () => false, dispose: () => undefined }

function loadToast(win: BrowserWindow): void {
  const devUrl = process.env.ELECTRON_RENDERER_URL
  if (devUrl) void win.loadURL(`${devUrl}/toast/index.html`)
  else void win.loadFile(path.join(__dirname, '../renderer/toast/index.html'))
}

export function registerToast(deps: ToastDeps): ToastHandle {
  const { ctx } = deps
  const env = process.env
  const disabled = deps.disabled ?? (env.ALONGSIDE_HEADLESS === '1' || env.ALONGSIDE_NO_OVERLAY === '1')
  if (disabled) return NOOP
  const capturable = deps.capturable ?? env.ALONGSIDE_OVERLAY_CAPTURABLE === '1'
  const timeoutMs = deps.confirmTimeoutMs ?? CONFIRM_TIMEOUT_MS
  const loadTimeoutMs = deps.loadTimeoutMs ?? LOAD_TIMEOUT_MS

  interface Live {
    id: string
    win: BrowserWindow
    shown: boolean
    notification: Notification | null
    release: () => void
    loadTimer: NodeJS.Timeout
    measureTimers: NodeJS.Timeout[]
  }
  let live: Live | null = null
  // A request is shown at most once: after it was shown, failed or dismissed here, it is never recreated.
  const handled = new Set<string>()
  let disposed = false

  const style = (): string => (env.ALONGSIDE_CONFIRM_STYLE === 'dock' ? 'dock' : ctx.settings.get().confirmStyle)

  const alive = (l: Live): boolean => !l.win.isDestroyed() && !l.win.webContents.isDestroyed()

  const bounds = (height: number) => {
    const wa = screen.getPrimaryDisplay().workArea // below the menu bar
    return { width: TOAST_WIDTH, height, x: wa.x + wa.width - TOAST_WIDTH - TOAST_MARGIN, y: wa.y + TOAST_MARGIN }
  }

  // The renderer's card height drives the window height (no extra IPC channel: main asks the page).
  const fit = (l: Live): void => {
    if (!alive(l)) return
    void l.win.webContents
      .executeJavaScript(`(() => { const c = document.querySelector('[data-toast-card]'); return c ? Math.ceil(c.getBoundingClientRect().height) : 0 })()`)
      .then((h) => {
        if (live !== l || !alive(l) || typeof h !== 'number' || h <= 0) return
        l.win.setBounds(bounds(Math.min(MAX_HEIGHT, Math.max(MIN_HEIGHT, h + 2 * TOAST_MARGIN + 4))))
      })
      .catch(() => undefined)
  }

  const push = (l: Live): void => {
    if (!alive(l)) return
    const s = ctx.state.get()
    // The toast needs only the request, the look-and-feel settings and the countdown; no captions or agent chips.
    l.win.webContents.send(IPC.stateUpdate, { ...s, captions: [], agents: [] } satisfies CompanionState)
  }

  const teardown = (reason: string): void => {
    const l = live
    if (!l) return
    live = null
    clearTimeout(l.loadTimer)
    l.measureTimers.forEach(clearTimeout)
    try {
      l.notification?.close()
    } catch {
      // the notification may already be gone
    }
    l.release()
    if (!l.win.isDestroyed()) l.win.destroy()
    if (ctx.state.get().toastConfirm) ctx.state.patch({ toastConfirm: undefined })
    ctx.log('toast', `hidden (${reason})`)
  }

  // The prompt must never be lost: drop the toast and let the dock show its own modal for this request.
  const fallBack = (l: Live, why: unknown): void => {
    ctx.log('toast', 'falling back to the dock prompt:', why instanceof Error ? why.message : String(why))
    if (live === l) teardown('fallback')
  }

  const raise = (l: Live): void => {
    if (live !== l || !alive(l)) return
    l.win.showInactive()
    l.win.moveTop()
  }

  const notify = (l: Live, request: ConfirmRequest): void => {
    try {
      if (!Notification.isSupported()) return
      const n = new Notification({ title: NOTIFICATION_TITLE, body: request.question.slice(0, 240), silent: false })
      n.on('click', () => raise(l))
      l.notification = n // kept alive until the toast goes: macOS drops click handlers of collected notifications
      n.show()
    } catch (err) {
      ctx.log('toast', 'native notification failed:', err instanceof Error ? err.message : String(err))
    }
  }

  const reveal = (l: Live, request: ConfirmRequest): void => {
    if (live !== l || l.shown || !alive(l)) return
    clearTimeout(l.loadTimer)
    l.shown = true
    l.win.setBounds(bounds(MIN_HEIGHT + 60))
    push(l)
    l.measureTimers = [60, 200, 600].map((ms) => setTimeout(() => fit(l), ms))
    fit(l)
    l.win.showInactive() // never takes focus from the app the assistant is working in
    notify(l, request)
  }

  const start = (request: ConfirmRequest): void => {
    handled.add(request.id)
    let l: Live | null = null
    try {
      const wa = screen.getPrimaryDisplay().workArea
      const win = new BrowserWindow({
        width: TOAST_WIDTH,
        height: MIN_HEIGHT,
        x: wa.x + wa.width - TOAST_WIDTH - TOAST_MARGIN,
        y: wa.y + TOAST_MARGIN,
        show: false,
        frame: false,
        transparent: true,
        backgroundColor: '#00000000',
        hasShadow: false,
        resizable: false,
        movable: false,
        minimizable: false,
        maximizable: false,
        fullscreenable: false,
        skipTaskbar: true,
        alwaysOnTop: true,
        ...(process.platform === 'darwin' ? { type: 'panel' as const } : {}),
        title: NOTIFICATION_TITLE,
        webPreferences: { preload: path.join(__dirname, '../preload/index.js'), contextIsolation: true, sandbox: true, nodeIntegration: false, backgroundThrottling: false },
      })
      const release = deps.adoptOwner?.(win.webContents.id) ?? (() => undefined)
      const made: Live = {
        id: request.id,
        win,
        shown: false,
        notification: null,
        release,
        loadTimer: setTimeout(() => fallBack(made, 'the toast page did not load in time'), loadTimeoutMs),
        measureTimers: [],
      }
      l = made
      live = made
      // Same level as the overlay, one step above it, on every Space and over full-screen apps.
      win.setAlwaysOnTop(true, 'screen-saver', 1)
      win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true, skipTransformProcessType: true })
      // Excluded from screen capture exactly like the overlay: the model must never see its own prompt.
      win.setContentProtection(!capturable)
      win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))
      win.webContents.on('will-navigate', (event) => event.preventDefault())
      win.webContents.on('did-finish-load', () => reveal(made, request))
      win.webContents.on('did-fail-load', (_e, code, description) => fallBack(made, `load failed ${code} ${description}`))
      win.webContents.on('render-process-gone', (_e, details) => fallBack(made, `renderer gone: ${details.reason}`))
      win.on('closed', () => {
        if (live === made) fallBack(made, 'window closed')
      })
      loadToast(win)
      // From here the dock shows no second prompt for this request (it would only if the toast later falls back).
      ctx.state.patch({ toastConfirm: { id: request.id, expiresAt: Date.now() + timeoutMs } })
    } catch (err) {
      if (l) fallBack(l, err)
      else ctx.log('toast', 'toast window could not be created; the dock shows the prompt:', err instanceof Error ? err.message : String(err))
    }
  }

  const onState = (s: CompanionState): void => {
    if (disposed) return
    const request = s.pendingConfirm
    if (!request) {
      if (live) teardown('cleared')
      return
    }
    if (live && live.id !== request.id) teardown('replaced') // a newer request supersedes
    if (live) {
      if (style() !== 'toast') {
        handled.add(request.id)
        teardown('style changed to dock')
      } else if (live.shown) push(live)
      return
    }
    if (handled.has(request.id) || style() !== 'toast') return
    start(request)
  }

  const off = ctx.state.subscribe(onState)
  onState(ctx.state.get())

  return {
    visible: () => live !== null && live.shown && alive(live) && live.win.isVisible(),
    dispose: () => {
      disposed = true
      off()
      teardown('dispose')
    },
  }
}
