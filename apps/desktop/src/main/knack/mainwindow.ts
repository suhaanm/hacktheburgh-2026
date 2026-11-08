// The Knack main window: a normal macOS window (hidden-inset title bar) that hosts the dashboard. It opens at the spec's size on the display the worker is on, remembers its
// size and position per display, and closes to the Dock: the app, the menu bar item and the Dock icon stay, the page stays alive for a fast reopen, and nothing is stopped.
//
// The behaviour is a controller over a small window port (`WindowPort`), so close, activate and restore are tested with a fake window; `createMainWindow` builds the
// real BrowserWindow and hands it over.
//
// Why a hidden-inset title bar: the dashboard has a left sidebar that starts at the top edge, so a separate title bar would be an empty strip above the wordmark. With
// the inset bar the traffic lights sit in the sidebar's top-left corner, the sidebar leaves room under them and its top 40 px drags the window
// (apps/dashboard/src/styles/shell.css, switched on by main.tsx when the preload says the platform is darwin). Off macOS the window has the standard frame.
import path from 'node:path'
import { BrowserWindow, nativeTheme, screen, shell } from 'electron'
import { APP_ORIGIN, WINDOW_TITLES } from '../../shared/brand'
import type { ShellUiState } from '../../shared/knack'
import { KNACK_IPC } from '../../shared/knack'
import { displayForBounds, minSizeFor, restoreBounds, type DisplayLike, type Rect } from './window-bounds'
import type { WindowStateStore } from './window-state'

export const STARTING_URL = `${APP_ORIGIN}/__shell/starting.html`

export type MainWindowEvent = 'focus' | 'blur' | 'show' | 'hide' | 'minimize' | 'restore'

export interface WindowSnapshot {
  exists: boolean
  /** On screen (not hidden to the Dock, not minimised). */
  visible: boolean
  minimised: boolean
  fullScreen: boolean
  focused: boolean
}

/** The slice of a BrowserWindow the controller uses. */
export interface WindowPort {
  show(): void
  showInactive(): void
  hide(): void
  focus(): void
  restore(): void
  minimize(): void
  isVisible(): boolean
  isMinimized(): boolean
  isFocused(): boolean
  isFullScreen(): boolean
  isDestroyed(): boolean
  getBounds(): Rect
  /** The page's own area on the screen (the window without its title bar). */
  getContentBounds(): Rect
  destroy(): void
  loadURL(url: string): void
  send(channel: string, ...args: unknown[]): void
  webContentsId(): number
  /** 'close' handlers may call preventDefault. */
  on(event: 'close', cb: (e: { preventDefault(): void }) => void): void
  on(event: 'resize' | 'move' | MainWindowEvent, cb: () => void): void
}

export interface MainWindowDeps {
  store: WindowStateStore
  displays: () => DisplayLike[]
  /** Never shown (the hidden check). */
  hidden: boolean
}

export interface MainWindow {
  window(): WindowPort | null
  /** The Dock icon, Activate, Open Knack, Review: open from closed, restore from minimised, or bring forward from behind; takes the keyboard. */
  show(): void
  /** Bring it back without taking the keyboard from the app the worker is in. */
  restoreQuietly(): void
  minimise(): void
  /** Close to the Dock: hide, keep the page alive. */
  hide(): void
  state(): WindowSnapshot
  loadStarting(): void
  loadDashboard(url: string): void
  pushUiState(s: ShellUiState): void
  /** The last state pushed to the starting page (it asks again when it loads: it may have missed the push). */
  uiState(): ShellUiState
  /** True for events from this window's page (for IPC sender checks). */
  owns(webContentsId: number): boolean
  isFocused(): boolean
  /** Window events the shell cares about. */
  subscribe(cb: (e: MainWindowEvent) => void): () => void
  /** The app is quitting: closing now really closes. */
  setQuitting(): void
  dispose(): void
}

export function createMainWindowController(win: WindowPort, deps: MainWindowDeps): MainWindow {
  let quitting = false
  let ui: ShellUiState = { kind: 'starting', text: '' }
  const listeners = new Set<(e: MainWindowEvent) => void>()
  for (const e of ['focus', 'blur', 'show', 'hide', 'minimize', 'restore'] as const) win.on(e, () => listeners.forEach((l) => l(e)))

  // Remember where the worker put it, per display (written once, 400 ms after the drag or resize settles).
  const remember = (): void => {
    if (win.isDestroyed() || win.isMinimized() || win.isFullScreen() || !win.isVisible()) return
    const b = win.getBounds()
    const d = displayForBounds(deps.displays(), b)
    if (d) deps.store.touch(d.id, b)
  }
  win.on('resize', remember)
  win.on('move', remember)

  // Cmd-W and the red button hide the window: the app, the Dock icon, the menu bar item, the page and any run carry on.
  win.on('close', (event) => {
    if (quitting) return
    event.preventDefault()
    win.hide()
  })

  const alive = (): boolean => !win.isDestroyed()
  const api: MainWindow = {
    window: () => (alive() ? win : null),
    show() {
      if (!alive() || deps.hidden) return // a hidden run (the check) never shows a window
      if (win.isMinimized()) win.restore()
      win.show()
      win.focus()
    },
    restoreQuietly() {
      if (!alive()) return
      if (win.isMinimized()) win.restore()
      if (!deps.hidden) win.showInactive()
    },
    minimise() {
      if (alive() && !win.isFullScreen()) win.minimize()
    },
    hide() {
      if (alive()) win.hide()
    },
    state: () => (alive() ? { exists: true, visible: win.isVisible() && !win.isMinimized(), minimised: win.isMinimized(), fullScreen: win.isFullScreen(), focused: win.isFocused() } : { exists: false, visible: false, minimised: false, fullScreen: false, focused: false }),
    loadStarting: () => alive() && win.loadURL(STARTING_URL),
    loadDashboard: (url) => alive() && win.loadURL(url),
    pushUiState(s) {
      ui = s
      if (alive()) win.send(KNACK_IPC.state, s)
    },
    uiState: () => ui,
    owns: (id) => alive() && win.webContentsId() === id,
    isFocused: () => alive() && win.isFocused(),
    subscribe(cb) {
      listeners.add(cb)
      return () => listeners.delete(cb)
    },
    setQuitting() {
      quitting = true
    },
    dispose() {
      deps.store.flush()
      if (alive()) win.destroy()
    },
  }
  return api
}

/** A launch at login shows no window, only the menu bar item and the Dock icon (the worker opens Knack when they want it); a hidden check never shows one either. */
export const showsAtStart = (o: { hidden: boolean; openedAtLogin: boolean }): boolean => !o.hidden && !o.openedAtLogin

export interface ElectronMainWindowDeps {
  store: WindowStateStore
  hidden: boolean
  /** The app was opened by the login item (app.getLoginItemSettings().wasOpenedAtLogin). */
  openedAtLogin?: boolean
  /** The dev server's origin, allowed for navigation in development; null in production. */
  devOrigin: string | null
}

const displays = (): DisplayLike[] => screen.getAllDisplays().map((d) => ({ id: d.id, workArea: d.workArea }))

/** The real window: the BrowserWindow, wrapped as a port, opened where `restoreBounds` says. */
export function createMainWindow(deps: ElectronMainWindowDeps): MainWindow {
  const all = displays()
  const primary = screen.getPrimaryDisplay()
  const where = restoreBounds({ displays: all, cursor: screen.getCursorScreenPoint(), saved: (id) => deps.store.get(id), lastDisplay: deps.store.lastDisplay() }) ?? { bounds: primary.workArea, displayId: primary.id, source: 'default' as const }
  const area = all.find((d) => d.id === where.displayId)?.workArea ?? primary.workArea
  const min = minSizeFor(area)
  const mac = process.platform === 'darwin'

  const win = new BrowserWindow({
    ...where.bounds,
    minWidth: min.width,
    minHeight: min.height,
    show: false,
    title: WINDOW_TITLES.main,
    // The window's own colour before the page paints: no white flash in dark mode. Solid, no vibrancy.
    backgroundColor: nativeTheme.shouldUseDarkColors ? '#0e1319' : '#f6f7f9',
    ...(mac ? { titleBarStyle: 'hiddenInset' as const, trafficLightPosition: { x: 16, y: 16 } } : {}),
    webPreferences: { preload: path.join(__dirname, '../preload/knack.js'), contextIsolation: true, sandbox: true, nodeIntegration: false, spellcheck: false },
  })
  if (showsAtStart({ hidden: deps.hidden, openedAtLogin: deps.openedAtLogin === true })) win.once('ready-to-show', () => win.show())

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

  // The page learns it is in the hidden-inset window (html[data-knack-shell="mac-inset"]), so the sidebar can leave room for the traffic lights and drag by its top edge.
  // Set from here, in every page of this window, so the dashboard needs nothing from the preload for it.
  if (mac) {
    win.webContents.on('dom-ready', () => {
      void win.webContents.executeJavaScript(`document.documentElement.dataset.knackShell = 'mac-inset'`).catch(() => undefined)
    })
  }

  const port: WindowPort = {
    show: () => win.show(),
    showInactive: () => win.showInactive(),
    hide: () => win.hide(),
    focus: () => win.focus(),
    restore: () => win.restore(),
    minimize: () => win.minimize(),
    isVisible: () => win.isVisible(),
    isMinimized: () => win.isMinimized(),
    isFocused: () => win.isFocused(),
    isFullScreen: () => win.isFullScreen(),
    isDestroyed: () => win.isDestroyed(),
    getBounds: () => win.getBounds(),
    getContentBounds: () => win.getContentBounds(),
    destroy: () => win.destroy(),
    loadURL: (url) => void win.loadURL(url),
    send: (channel, ...args) => {
      if (!win.webContents.isDestroyed()) win.webContents.send(channel, ...args)
    },
    webContentsId: () => win.webContents.id,
    on: ((event: string, cb: (e: { preventDefault(): void }) => void) => void (win as unknown as { on(e: string, c: (e: { preventDefault(): void }) => void): void }).on(event, cb)) as WindowPort['on'],
  }
  const ctrl = createMainWindowController(port, { store: deps.store, displays, hidden: deps.hidden })
  // The starting page may have loaded after the last push: send it the current state again.
  win.webContents.on('did-finish-load', () => {
    if (!win.isDestroyed() && win.webContents.getURL().startsWith(STARTING_URL)) ctrl.pushUiState(ctrl.uiState())
  })
  return ctrl
}
