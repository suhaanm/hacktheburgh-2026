// The Knack main window: a normal macOS window (hidden-inset title bar) that hosts the dashboard. It opens at a calm size on the display the worker is on,
// remembers its size and position per display, and closes to the menu bar: the app keeps running, and the Dock icon or the menu bar item brings it back.
//
// Why a hidden-inset title bar: the dashboard has a left sidebar that starts at the top edge, so a separate title bar would be an empty grey strip above
// the wordmark. With the inset bar the traffic lights sit in the sidebar's top-left corner, the sidebar leaves room under them and the top of it drags the
// window (apps/dashboard/src/styles/shell.css, switched on by the preload's data-knack-shell attribute). Off macOS the window has the standard frame.
import path from 'node:path'
import { BrowserWindow, nativeTheme, screen, shell } from 'electron'
import { APP_ORIGIN, WINDOW_TITLES } from '../../shared/brand'
import type { ShellUiState } from '../../shared/knack'
import { KNACK_IPC } from '../../shared/knack'
import { displayAtPoint, displayForBounds, initialBounds, minSizeFor, type DisplayLike } from './window-bounds'
import type { WindowStateStore } from './window-state'
import type { ShellWindowState } from './shell-rules'

export const STARTING_URL = `${APP_ORIGIN}/__shell/starting.html`

export type MainWindowEvent = 'focus' | 'blur' | 'show' | 'hide' | 'minimize' | 'restore'

export interface MainWindowDeps {
  store: WindowStateStore
  /** Never shown (the hidden check). */
  hidden: boolean
  /** The dev server's origin, allowed for navigation in development; null in production. */
  devOrigin: string | null
  log?: (...args: unknown[]) => void
}

export interface MainWindow {
  window(): BrowserWindow | null
  /** Bring it forward: restore if minimised, show if hidden to the menu bar, take the keyboard. */
  show(): void
  /** Bring it back without taking the keyboard from the app the worker is in. */
  restoreQuietly(): void
  minimise(): void
  state(): ShellWindowState
  loadStarting(): void
  loadDashboard(url: string): void
  pushUiState(s: ShellUiState): void
  /** True for events from this window's page (for IPC sender checks). */
  owns(webContentsId: number): boolean
  isFocused(): boolean
  /** Window events the shell cares about: it comes forward or goes away, or gains or loses the keyboard. */
  subscribe(cb: (e: MainWindowEvent) => void): () => void
  /** The app is quitting: closing now really closes. */
  setQuitting(): void
  dispose(): void
}

const displays = (): (DisplayLike & { raw: Electron.Display })[] => screen.getAllDisplays().map((d) => ({ id: d.id, workArea: d.workArea, raw: d }))

export function createMainWindow(deps: MainWindowDeps): MainWindow {
  const all = displays()
  const primary = screen.getPrimaryDisplay()
  const at = displayAtPoint(all, screen.getCursorScreenPoint()) ?? { id: primary.id, workArea: primary.workArea, raw: primary }
  const bounds = initialBounds(at.workArea, deps.store.get(at.id))
  const min = minSizeFor(at.workArea)
  const mac = process.platform === 'darwin'
  let quitting = false

  const win = new BrowserWindow({
    ...bounds,
    minWidth: min.width,
    minHeight: min.height,
    show: false,
    title: WINDOW_TITLES.main,
    // The window's own colour before the page paints: no white flash in dark mode.
    backgroundColor: nativeTheme.shouldUseDarkColors ? '#0e1319' : '#f6f7f9',
    ...(mac ? { titleBarStyle: 'hiddenInset' as const, trafficLightPosition: { x: 16, y: 16 } } : {}),
    webPreferences: {
      preload: path.join(__dirname, '../preload/knack.js'),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
      spellcheck: false,
    },
  })

  if (!deps.hidden) win.once('ready-to-show', () => win.show())

  // Remember where the worker put it, per display (written once after the drag or resize settles).
  const remember = (): void => {
    if (win.isDestroyed() || win.isMinimized() || win.isFullScreen() || !win.isVisible()) return
    const b = win.getBounds()
    const d = displayForBounds(displays(), b)
    if (d) deps.store.touch(d.id, b)
  }
  win.on('resize', remember)
  win.on('move', remember)

  const listeners = new Set<(e: MainWindowEvent) => void>()
  for (const e of ['focus', 'blur', 'show', 'hide', 'minimize', 'restore'] as const) win.on(e as 'focus', () => listeners.forEach((l) => l(e)))

  // Cmd-W and the red button close to the menu bar: the app, the services and the pill keep going.
  win.on('close', (event) => {
    if (quitting) return
    event.preventDefault()
    win.hide()
  })

  // The page may only be the dashboard (or our own starting page): any other address opens in the worker's browser, never in this window.
  const allowed = (url: string): boolean => {
    try {
      const o = new URL(url).origin
      return o === APP_ORIGIN || (deps.devOrigin !== null && o === deps.devOrigin)
    } catch {
      return false
    }
  }
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//i.test(url) && !allowed(url)) void shell.openExternal(url).catch(() => undefined)
    return { action: 'deny' }
  })
  win.webContents.on('will-navigate', (event, url) => {
    if (allowed(url)) return
    event.preventDefault()
    if (/^https?:\/\//i.test(url)) void shell.openExternal(url).catch(() => undefined)
  })

  let ui: ShellUiState = { kind: 'starting', text: '' }
  const alive = (): boolean => !win.isDestroyed() && !win.webContents.isDestroyed()

  const api: MainWindow = {
    window: () => (win.isDestroyed() ? null : win),
    show() {
      if (win.isDestroyed()) return
      if (win.isMinimized()) win.restore()
      win.show()
      win.focus()
    },
    restoreQuietly() {
      if (win.isDestroyed()) return
      if (win.isMinimized()) win.restore()
      if (!deps.hidden) win.showInactive()
    },
    minimise() {
      if (!win.isDestroyed() && !win.isFullScreen()) win.minimize()
    },
    state: () => (win.isDestroyed() ? { exists: false, visible: false, minimised: false, fullScreen: false } : { exists: true, visible: win.isVisible() || win.isMinimized(), minimised: win.isMinimized(), fullScreen: win.isFullScreen() }),
    loadStarting: () => void win.loadURL(STARTING_URL),
    loadDashboard: (url) => void win.loadURL(url),
    pushUiState(s) {
      ui = s
      if (alive()) win.webContents.send(KNACK_IPC.state, s)
    },
    owns: (id) => !win.isDestroyed() && win.webContents.id === id,
    isFocused: () => !win.isDestroyed() && win.isFocused(),
    subscribe(cb) {
      listeners.add(cb)
      return () => listeners.delete(cb)
    },
    setQuitting() {
      quitting = true
    },
    dispose() {
      deps.store.flush()
      if (!win.isDestroyed()) win.destroy()
    },
  }
  // The page asks for the current state when it loads (it may have missed the push).
  win.webContents.on('did-finish-load', () => {
    if (alive() && win.webContents.getURL().startsWith(STARTING_URL)) win.webContents.send(KNACK_IPC.state, ui)
  })
  return api
}
