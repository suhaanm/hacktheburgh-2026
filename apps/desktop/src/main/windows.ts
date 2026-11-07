import path from 'node:path'
import { app, BrowserWindow, screen, session, shell } from 'electron'
import type { DockMode, EventArgs, EventChannel } from '../shared/ipc'
import { configureOverlayWindow } from './capture/overlay-window'

export interface WindowOptions {
  noOverlay: boolean
  headless: boolean
  // SHELL2: when false the dock window is created but kept hidden (the renderer still runs: mic, wake spotter, Live session).
  showDockAtStart?: boolean
}

export interface Windows {
  sendDock<C extends EventChannel>(channel: C, ...args: EventArgs<C>): void
  sendOverlay<C extends EventChannel>(channel: C, ...args: EventArgs<C>): void
  broadcast<C extends EventChannel>(channel: C, ...args: EventArgs<C>): void
  setDockMode(mode: DockMode): void
  // SHELL (menu bar): the dock window itself can be hidden and brought back; closing it only hides it.
  showDock(): void
  hideDock(): void
  isDockVisible(): boolean
  getDockMode(): DockMode
  owns(webContentsId: number): boolean
  overlayPng(): Promise<Buffer | null>
  dockPng(): Promise<Buffer | null>
  overlaySize(): { width: number; height: number } | null
}

const DOCK_SIZES: Record<DockMode, { width: number; height: number }> = {
  compact: { width: 320, height: 64 },
  expanded: { width: 360, height: 580 },
}
const MARGIN = 16

// NOTIFY: extra windows of ours (the confirmation toast) whose IPC owns() should accept. Returns the undo.
const adoptedOwners = new Set<number>()
export function adoptOwner(webContentsId: number): () => void {
  adoptedOwners.add(webContentsId)
  return () => void adoptedOwners.delete(webContentsId)
}

function loadRenderer(win: BrowserWindow, entry: 'dock' | 'overlay'): void {
  const devUrl = process.env.ELECTRON_RENDERER_URL
  if (devUrl) void win.loadURL(`${devUrl}/${entry}/index.html`)
  else void win.loadFile(path.join(__dirname, `../renderer/${entry}/index.html`))
}

function preloadPath(): string {
  return path.join(__dirname, '../preload/index.js')
}

export function createWindows(opts: WindowOptions): Windows {
  const display = screen.getPrimaryDisplay()
  let dockMode: DockMode = 'compact'

  const dockBounds = (mode: DockMode) => {
    const { width, height } = DOCK_SIZES[mode]
    const wa = display.workArea
    return { width, height, x: wa.x + wa.width - width - MARGIN, y: wa.y + wa.height - height - MARGIN }
  }

  const dock = new BrowserWindow({
    ...dockBounds(dockMode),
    show: false,
    frame: false,
    resizable: false,
    fullscreenable: false,
    alwaysOnTop: true,
    skipTaskbar: false,
    // Transparent so the dock's "glass" setting can show the desktop (macOS vibrancy blurs it); the page paints solid when glass is off.
    transparent: true,
    backgroundColor: '#00000000',
    ...(process.platform === 'darwin' ? { vibrancy: 'under-window' as const, visualEffectState: 'active' as const } : {}),
    title: 'Alongside',
    webPreferences: {
      preload: preloadPath(),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
      backgroundThrottling: false,
      // AudioContext and getUserMedia must work without a prior click (the wake spotter starts on its own).
      autoplayPolicy: 'no-user-gesture-required',
    },
  })
  dock.setAlwaysOnTop(true, 'floating')
  dock.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true })
  loadRenderer(dock, 'dock')
  if (!opts.headless && opts.showDockAtStart !== false) dock.once('ready-to-show', () => dock.showInactive())

  let overlay: BrowserWindow | null = null
  if (!opts.noOverlay) {
    const { x, y, width, height } = display.bounds
    overlay = new BrowserWindow({
      x,
      y,
      width,
      height,
      show: false,
      transparent: true,
      frame: false,
      hasShadow: false,
      focusable: false,
      resizable: false,
      movable: false,
      fullscreenable: false,
      skipTaskbar: true,
      alwaysOnTop: true,
      enableLargerThanScreen: true,
      ...(process.platform === 'darwin' ? { type: 'panel' as const } : {}),
      webPreferences: { preload: preloadPath(), contextIsolation: true, sandbox: true, nodeIntegration: false, backgroundThrottling: false },
    })
    overlay.setIgnoreMouseEvents(true)
    overlay.setAlwaysOnTop(true, 'screen-saver')
    overlay.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true, skipTransformProcessType: true })
    overlay.setBounds({ x, y, width, height })
    configureOverlayWindow(overlay)
    loadRenderer(overlay, 'overlay')
    if (!opts.headless) overlay.once('ready-to-show', () => overlay?.showInactive())
  }

  // Our windows never navigate away from the bundled UI and never open new windows (a link or script cannot load a remote page into them).
  for (const win of [dock, overlay]) {
    if (!win) continue
    // Never a new window; a plain http(s) link goes to the user's browser, anything else is dropped.
    win.webContents.setWindowOpenHandler(({ url }) => {
      if (/^https?:\/\//i.test(url)) void shell.openExternal(url).catch(() => undefined)
      return { action: 'deny' }
    })
    win.webContents.on('will-navigate', (event) => event.preventDefault())
  }

  // Our own windows may use the mic/camera/screen; nothing else may.
  const ours = (id: number | undefined) => id !== undefined && (id === dock.webContents.id || id === overlay?.webContents.id)
  // NOTIFY: the toast window may use our IPC (answer a confirm) but gets no mic/screen permission, so only owns() knows it.
  const ownsOrAdopted = (id: number | undefined) => ours(id) || (id !== undefined && adoptedOwners.has(id))
  session.defaultSession.setPermissionRequestHandler((wc, permission, callback) => {
    callback(ours(wc?.id) && ['media', 'display-capture', 'mediaKeyboardLock'].includes(permission))
  })
  session.defaultSession.setPermissionCheckHandler((wc, permission) => ours(wc?.id) && ['media', 'display-capture'].includes(permission))

  const safeSend = (win: BrowserWindow | null, channel: string, args: unknown[]) => {
    if (win && !win.isDestroyed() && !win.webContents.isDestroyed()) win.webContents.send(channel, ...args)
  }

  const capture = async (win: BrowserWindow | null) => {
    if (!win || win.isDestroyed()) return null
    return (await win.webContents.capturePage()).toPNG()
  }

  // The app lives in the menu bar: closing the dock only hides it. Quit (tray, Cmd+Q) destroys it below.
  let quitting = false
  dock.on('close', (event) => {
    if (quitting) return
    event.preventDefault()
    dock.hide()
  })

  app.on('before-quit', () => {
    quitting = true
    dock.destroy()
    overlay?.destroy()
  })

  return {
    sendDock: (channel, ...args) => safeSend(dock, channel, args),
    sendOverlay: (channel, ...args) => safeSend(overlay, channel, args),
    broadcast: (channel, ...args) => {
      safeSend(dock, channel, args)
      safeSend(overlay, channel, args)
    },
    setDockMode(mode) {
      if (mode === dockMode) return
      dockMode = mode
      dock.setBounds(dockBounds(mode), true)
    },
    showDock() {
      if (dock.isDestroyed()) return
      dock.show()
    },
    hideDock() {
      if (!dock.isDestroyed()) dock.hide()
    },
    isDockVisible: () => !dock.isDestroyed() && dock.isVisible(),
    getDockMode: () => dockMode,
    owns: ownsOrAdopted,
    overlayPng: () => capture(overlay),
    dockPng: () => capture(dock),
    overlaySize: () => (overlay ? overlay.getBounds() : null),
  }
}
