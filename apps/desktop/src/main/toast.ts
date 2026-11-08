// NOTIFY: permission prompts (ConfirmRequest in state.pendingConfirm) as a macOS-style toast at the top-right of the screen,
// plus one native notification. The toast is a separate small window; it only DISPLAYS the request. An approval can still only
// arrive as a real click (IPC confirm:answer, validated against the request id and its two options by ConfirmBroker).
import path from 'node:path'
import { BrowserWindow, Notification, screen } from 'electron'
import { IPC } from '../shared/ipc'
import type { CompanionState, ConfirmRequest } from '../shared/protocol'
import { acquireWithin, type VoiceLock } from './attention/lock'
import { CONFIRM_TIMEOUT_MS } from './confirm'
import type { ServiceContext } from './context'
import { APP_NAME } from '../shared/brand'

export const TOAST_WIDTH = 400
export const TOAST_MARGIN = 12
const MIN_HEIGHT = 140
const MAX_HEIGHT = 560
const LOAD_TIMEOUT_MS = 4000
const FOLLOW_MS = 400
export const NOTIFICATION_TITLE = `${APP_NAME} needs your OK`

// KNACK: in the Knack app the prompt is a corner card, not a top-right toast: bottom-right of the work area, 16 px in, stacked above the corner pill column when that
// is showing, so there is one place in one corner where Knack asks for anything. The page puts its card 12 px inside the window on the left, top and right and 16 px
// inside at the bottom (the window is the card's height plus 2 x 12 + 4), and the corner column's window keeps 3 px around its own card.
export const CORNER_MARGIN = 16
export const CORNER_GAP = 8
const PAGE_INSET = TOAST_MARGIN // body padding in toast.css
const PAGE_INSET_BOTTOM = TOAST_MARGIN + 4
const COLUMN_INSET = 3

export interface Rect {
  x: number
  y: number
  width: number
  height: number
}

/** The window bounds of the corner card: its card's right edge CORNER_MARGIN from the work area's, its bottom edge CORNER_MARGIN above the work area's bottom, or CORNER_GAP above the corner column when it shows. */
export function toastCornerBounds(workArea: Rect, height: number, column: Rect | null): Rect {
  const cardBottom = column ? column.y + COLUMN_INSET - CORNER_GAP : workArea.y + workArea.height - CORNER_MARGIN
  const windowBottom = cardBottom + PAGE_INSET_BOTTOM
  return { width: TOAST_WIDTH, height, x: workArea.x + workArea.width - TOAST_WIDTH + PAGE_INSET - CORNER_MARGIN, y: Math.max(workArea.y, windowBottom - height) }
}

export interface ToastCorner {
  /** The corner pill column's window bounds while it is showing (the card goes above it), else null. */
  column(): Rect | null
}

// REQ-8: a permission prompt is the ConfirmBroker's own surface and is never gated or delayed by the attention router. It only takes the
// LOCAL one-voice lock (owner 'decision') so a cue or a notice cannot appear over it: it waits a moment for one that is up, then draws anyway.
export interface ToastAttention {
  lock: VoiceLock
}
export const LOCK_WAIT_MS = 3_000

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
  // The attention layer's lock. Absent: nothing changes. `setAttention` binds it later (the layer starts after the toast exists).
  attention?: ToastAttention | null
  lockWaitMs?: number
  // KNACK: place the prompt as a corner card (bottom-right, above the corner pill column). Absent: the top-right toast, as before.
  corner?: ToastCorner
}

export interface ToastHandle {
  visible(): boolean
  setAttention(a: ToastAttention | null): void
  dispose(): void
}

const NOOP: ToastHandle = { visible: () => false, setAttention: () => undefined, dispose: () => undefined }

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
    follow: NodeJS.Timeout | null // the corner card only: re-places the card when the corner column below it changes
  }
  let live: Live | null = null
  let attention: ToastAttention | null = deps.attention ?? null
  const lockWaitMs = deps.lockWaitMs ?? LOCK_WAIT_MS
  // The request ids this toast holds the voice lock for (released when the toast goes).
  const held = new Set<string>()
  const releaseVoice = (id: string): void => {
    if (held.delete(id)) attention?.lock.release('decision', id)
  }
  // A request is shown at most once: after it was shown, failed or dismissed here, it is never recreated.
  const handled = new Set<string>()
  let disposed = false

  const style = (): string => (env.ALONGSIDE_CONFIRM_STYLE === 'dock' ? 'dock' : ctx.settings.get().confirmStyle)

  const alive = (l: Live): boolean => !l.win.isDestroyed() && !l.win.webContents.isDestroyed()

  const bounds = (height: number) => {
    if (deps.corner) {
      // The display holding the corner column, or the one holding the pointer when there is none (the corner pill picks its display the same way).
      const column = deps.corner.column()
      const display = column ? screen.getDisplayMatching(column) : screen.getDisplayNearestPoint(screen.getCursorScreenPoint())
      return toastCornerBounds(display.workArea, height, column)
    }
    const wa = screen.getPrimaryDisplay().workArea // below the menu bar
    return { width: TOAST_WIDTH, height, x: wa.x + wa.width - TOAST_WIDTH - TOAST_MARGIN, y: wa.y + TOAST_MARGIN }
  }
  // The height the page last asked for: the card is re-placed when the corner column below it appears, grows or goes.
  let lastHeight = MIN_HEIGHT
  const placeAt = (l: Live, height: number): void => {
    lastHeight = height
    if (alive(l)) l.win.setBounds(bounds(height))
  }
  // Re-place only when the corner column moved the card's spot (a window per setBounds call is cheap, but a steady stream of them would flicker).
  const follow = (l: Live): void => {
    if (!deps.corner || l.follow) return
    let at = JSON.stringify(bounds(lastHeight))
    l.follow = setInterval(() => {
      if (live !== l || !alive(l)) return
      const next = JSON.stringify(bounds(lastHeight))
      if (next === at) return
      at = next
      l.win.setBounds(bounds(lastHeight))
    }, FOLLOW_MS)
  }

  // The renderer's card height drives the window height (no extra IPC channel: main asks the page).
  const fit = (l: Live): void => {
    if (!alive(l)) return
    void l.win.webContents
      .executeJavaScript(`(() => { const c = document.querySelector('[data-toast-card]'); return c ? Math.ceil(c.getBoundingClientRect().height) : 0 })()`)
      .then((h) => {
        if (live !== l || !alive(l) || typeof h !== 'number' || h <= 0) return
        placeAt(l, Math.min(MAX_HEIGHT, Math.max(MIN_HEIGHT, h + 2 * TOAST_MARGIN + 4)))
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
    if (l.follow) clearInterval(l.follow)
    try {
      l.notification?.close()
    } catch {
      // the notification may already be gone
    }
    l.release()
    releaseVoice(l.id)
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
    placeAt(l, MIN_HEIGHT + 60)
    follow(l)
    push(l)
    l.measureTimers = [60, 200, 600].map((ms) => setTimeout(() => fit(l), ms))
    fit(l)
    l.win.showInactive() // never takes focus from the app the assistant is working in
    notify(l, request)
  }

  const open = (request: ConfirmRequest): void => {
    let l: Live | null = null
    try {
      const first = bounds(MIN_HEIGHT)
      const win = new BrowserWindow({
        width: first.width,
        height: first.height,
        x: first.x,
        y: first.y,
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
        follow: null,
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
      else {
        releaseVoice(request.id)
        ctx.log('toast', 'toast window could not be created; the dock shows the prompt:', err instanceof Error ? err.message : String(err))
      }
    }
  }

  const start = (request: ConfirmRequest): void => {
    handled.add(request.id)
    const layer = attention
    if (!layer) return open(request)
    // The voice is free: draw now, with no delay at all. Otherwise wait a moment for the cue or notice that is up, then draw anyway.
    if (layer.lock.acquire('decision', timeoutMs, undefined, request.id)) {
      held.add(request.id)
      return open(request)
    }
    void acquireWithin(layer.lock, 'decision', timeoutMs, lockWaitMs, request.id).then((got) => {
      if (got) held.add(request.id)
      // Cleared, answered or replaced while it waited: nothing to draw (and the voice, if it was taken, goes back).
      if (disposed || live || ctx.state.get().pendingConfirm?.id !== request.id) return releaseVoice(request.id)
      open(request)
    })
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
    setAttention(a) {
      attention = a
    },
    dispose: () => {
      disposed = true
      off()
      teardown('dispose')
    },
  }
}
