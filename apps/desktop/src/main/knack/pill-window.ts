// The corner pill's window: a 280 by 44 panel at the bottom-right of the display where the work is happening, 85% opaque, always on top, never takes the
// keyboard, hidden from screen capture (the model must not see its own controls), invisible in full-screen Spaces, and click-through everywhere except the Stop
// button and the label. It has its own preload (src/preload/pill.ts) with four calls; main checks the sender on every message.
//
// Whether it may be on screen at all is decided elsewhere (pill-visibility.ts: never over a secure input or a denylisted app). This file only shows, moves
// and hides the window.
import path from 'node:path'
import { BrowserWindow, ipcMain, screen } from 'electron'
import { WINDOW_TITLES } from '../../shared/brand'
import { EMPTY_PILL_VIEW, PILL_IPC, type PillActionDto, type PillViewDto } from '../../shared/knack'
import { PILL_OPACITY, PILL_SIZE, pillBounds, workDisplay } from './pill-visibility'
import type { Rect } from './window-bounds'

export interface PillWindowDeps {
  /** Never shown (the hidden check). */
  hidden: boolean
  /** ALONGSIDE_OVERLAY_CAPTURABLE=1 (recording a demo): the pill may appear in captures. */
  capturable?: boolean
  onAction(a: PillActionDto): void
  log?: (...args: unknown[]) => void
}

export interface PillWindow {
  /** Send the view to the page. */
  push(view: PillViewDto): void
  /** Show at the bottom-right of the display where the work is, without taking focus. */
  show(): void
  hide(): void
  isVisible(): boolean
  /** The rectangle the pill occupies (null while hidden). */
  bounds(): Rect | null
  /** A picture of the page (for the hidden check); never used while the app runs. */
  png(): Promise<Buffer | null>
  /** Whether the window passes clicks through right now. */
  clickThrough(): boolean
  window(): BrowserWindow | null
  dispose(): void
}

const SAFE_ACTIONS = new Set(['stop', 'open'])

export function createPillWindow(deps: PillWindowDeps): PillWindow {
  const win = new BrowserWindow({
    ...pillBounds(screen.getPrimaryDisplay().workArea),
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
    focusable: false, // never takes the keyboard from the app the worker is in
    skipTaskbar: true,
    alwaysOnTop: true,
    ...(process.platform === 'darwin' ? { type: 'panel' as const } : {}),
    title: WINDOW_TITLES.pill,
    webPreferences: { preload: path.join(__dirname, '../preload/pill.js'), contextIsolation: true, sandbox: true, nodeIntegration: false, backgroundThrottling: false },
  })
  win.setAlwaysOnTop(true, 'floating')
  // Present on every desktop, but NOT over a full-screen app or presentation (visibleOnFullScreen false).
  win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: false, skipTransformProcessType: true })
  win.setContentProtection(!(deps.capturable ?? process.env.ALONGSIDE_OVERLAY_CAPTURABLE === '1'))
  win.setOpacity(PILL_OPACITY)
  // Click-through, but still told where the pointer is so the page can ask for clicks over the Stop button and the label.
  win.setIgnoreMouseEvents(true, { forward: true })
  let passThrough = true
  win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))
  win.webContents.on('will-navigate', (event) => event.preventDefault())

  let view: PillViewDto = EMPTY_PILL_VIEW
  let shownAt: Rect | null = null
  // Whether the shell wants it on screen (also true in a hidden run, where the window itself is never shown).
  let wanted = false
  const alive = (): boolean => !win.isDestroyed() && !win.webContents.isDestroyed()
  const fromPill = (event: { sender: { id: number } }): boolean => alive() && event.sender.id === win.webContents.id

  ipcMain.handle(PILL_IPC.get, (event) => {
    if (!fromPill(event)) throw new Error('pill IPC from an unknown sender')
    return view
  })
  ipcMain.on(PILL_IPC.action, (event, raw: unknown) => {
    if (!fromPill(event)) return
    const type = typeof raw === 'object' && raw !== null ? (raw as { type?: unknown }).type : undefined
    if (typeof type !== 'string' || !SAFE_ACTIONS.has(type)) return
    // A button that is not on screen cannot be pressed: Stop only while something works.
    if (type === 'stop' && !view.stop) return
    if (type === 'open' && !view.open) return
    deps.onAction({ type } as PillActionDto)
  })
  ipcMain.on(PILL_IPC.interactive, (event, on: unknown) => {
    if (!fromPill(event) || !alive()) return
    const takeClicks = on === true && (view.stop || view.open)
    if (takeClicks === !passThrough) return
    passThrough = !takeClicks
    win.setIgnoreMouseEvents(passThrough, { forward: true })
  })

  const devUrl = process.env.ELECTRON_RENDERER_URL
  if (devUrl) void win.loadURL(`${devUrl}/pill/index.html`)
  else void win.loadFile(path.join(__dirname, '../renderer/pill/index.html'))
  win.webContents.on('did-finish-load', () => {
    if (alive()) win.webContents.send(PILL_IPC.state, view)
  })

  return {
    push(next) {
      view = next
      if (alive()) win.webContents.send(PILL_IPC.state, next)
      // Nothing on the pill to press: make sure it lets everything through.
      if (!next.stop && !next.open && !passThrough && alive()) {
        passThrough = true
        win.setIgnoreMouseEvents(true, { forward: true })
      }
    },
    show() {
      if (!alive()) return
      const displays = screen.getAllDisplays().map((d) => ({ id: d.id, workArea: d.workArea }))
      const d = workDisplay(displays, screen.getCursorScreenPoint(), { id: screen.getPrimaryDisplay().id, workArea: screen.getPrimaryDisplay().workArea })
      const target = pillBounds(d.workArea, PILL_SIZE)
      if (!shownAt || shownAt.x !== target.x || shownAt.y !== target.y) win.setBounds(target)
      shownAt = target
      wanted = true
      if (!deps.hidden && !win.isVisible()) win.showInactive()
    },
    hide() {
      shownAt = null
      wanted = false
      if (alive() && win.isVisible()) win.hide()
    },
    isVisible: () => alive() && wanted,
    bounds: () => (alive() && wanted ? shownAt : null),
    png: async () => (alive() ? (await win.webContents.capturePage()).toPNG() : null),
    clickThrough: () => passThrough,
    window: () => (alive() ? win : null),
    dispose() {
      ipcMain.removeHandler(PILL_IPC.get)
      ipcMain.removeAllListeners(PILL_IPC.action)
      ipcMain.removeAllListeners(PILL_IPC.interactive)
      if (!win.isDestroyed()) win.destroy()
    },
  }
}
