// The background agent pills window: a second, small overlay column at the top right of the screen (16 px in, below the menu bar), one pill per task or run that is working, with an
// animated icon, its words, a quiet mark when it ends that fades, at most four and then "+n". It never takes the keyboard, never covers the menu bar, and is hidden from screen
// capture by the same rule as the other overlays (ALONGSIDE_OVERLAY_CAPTURABLE). A click on a pill opens Knack on that work; the stop button of a task stops it. The bottom-right
// corner column stays for Knack's own attention (approvals, voice, Stop); this one is only the work going on in the background.
//
// Data: ONE function, `source.onAgentRuns(cb)` (agent-pills-model.ts). Nothing else reaches this window.
import path from 'node:path'
import { BrowserWindow, ipcMain, screen } from 'electron'
import { PILLS_IPC, PILLS_WIDTH, pillIdOf, pillsBounds, pillsWindowHeight } from './agent-pills-ipc'
import { EMPTY_PILLS, createPillsModel, type AgentRunsSource, type PillItem, type PillsModel, type PillsView } from './agent-pills-model'

export interface AgentPillsOptions {
  source: AgentRunsSource
  /** A pill was clicked: open Knack on that work (the shell decides where: Routines, or Needs you when the work waits for an OK). */
  onOpen: (item: PillItem) => void
  /** The stop button of a task's pill. */
  onStop: (id: string) => void
  /** The window is built and works but is never shown (the hidden check). */
  hidden?: boolean
  disabled?: boolean
  capturable?: boolean
  log?: (scope: string, ...args: unknown[]) => void
  now?: () => number
  setTimer?: (fn: () => void, ms: number) => unknown
  clearTimer?: (h: unknown) => void
}

export interface AgentPills {
  view(): PillsView
  window(): BrowserWindow | null
  png(): Promise<Buffer | null>
  dispose(): void
}

export function createAgentPills(o: AgentPillsOptions): AgentPills {
  const env = process.env
  const disabled = o.disabled ?? (env.ALONGSIDE_HEADLESS === '1' || env.ALONGSIDE_NO_OVERLAY === '1')
  const capturable = o.capturable ?? env.ALONGSIDE_OVERLAY_CAPTURABLE === '1'
  const log = o.log ?? (() => undefined)
  let view: PillsView = EMPTY_PILLS
  let win: BrowserWindow | null = null
  let loaded = false
  let height = 40
  let displayId: number | null = null

  const alive = (): boolean => win !== null && !win.isDestroyed() && !win.webContents.isDestroyed()
  const fromPills = (e: { sender: { id: number } }): boolean => alive() && e.sender.id === (win as BrowserWindow).webContents.id

  /** The display holding the pointer when the first pill appears; it stays there until the column is empty again. */
  const workArea = () => {
    const all = screen.getAllDisplays()
    const found = displayId !== null ? all.find((d) => d.id === displayId) : undefined
    const chosen = found ?? screen.getDisplayNearestPoint(screen.getCursorScreenPoint())
    displayId = chosen.id
    return chosen.workArea
  }
  const place = (): void => {
    if (alive()) (win as BrowserWindow).setBounds(pillsBounds(workArea(), height))
  }
  const push = (): void => {
    if (alive() && loaded) (win as BrowserWindow).webContents.send(PILLS_IPC.state, view)
  }

  const ensure = (): void => {
    if (win || disabled) return
    const first = pillsBounds({ x: 0, y: 25, width: 1440, height: 875 }, height)
    const w = new BrowserWindow({
      width: PILLS_WIDTH,
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
      focusable: false, // never takes the keyboard from the app the worker is in
      skipTaskbar: true,
      alwaysOnTop: true,
      ...(process.platform === 'darwin' ? { type: 'panel' as const } : {}),
      title: 'Knack background work',
      webPreferences: { preload: path.join(__dirname, '../preload/pills.js'), contextIsolation: true, sandbox: true, nodeIntegration: false, backgroundThrottling: false },
    })
    win = w
    w.setAlwaysOnTop(true, 'screen-saver', 1)
    w.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true, skipTransformProcessType: true })
    w.setContentProtection(!capturable)
    w.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))
    w.webContents.on('will-navigate', (event) => event.preventDefault())
    w.webContents.on('did-finish-load', () => {
      loaded = true
      push()
    })
    w.on('closed', () => {
      win = null
      loaded = false
    })
    const devUrl = env.ELECTRON_RENDERER_URL
    if (devUrl) void w.loadURL(`${devUrl}/pills/index.html`)
    else void w.loadFile(path.join(__dirname, '../renderer/pills/index.html'))
  }

  const model: PillsModel = createPillsModel({
    now: o.now,
    setTimer: o.setTimer,
    clearTimer: o.clearTimer,
    onChange: (v) => {
      view = v
      if (v.items.length === 0) {
        // Nothing to show: the window goes away, so no invisible patch of screen is left over other apps.
        if (alive() && (win as BrowserWindow).isVisible()) (win as BrowserWindow).hide()
        displayId = null
        height = 40
        push()
        return
      }
      ensure()
      push()
      if (alive() && !o.hidden && !(win as BrowserWindow).isVisible()) {
        place()
        ;(win as BrowserWindow).showInactive()
      }
    },
  })
  const off = o.source.onAgentRuns((runs) => model.update(runs))
  // A display unplugged, plugged in or changed while the pills are up: back to the top right of a display that is there.
  const replace = (): void => {
    displayId = null
    if (alive() && (win as BrowserWindow).isVisible()) place()
  }
  if (!disabled) {
    screen.on('display-added', replace)
    screen.on('display-removed', replace)
    screen.on('display-metrics-changed', replace)
  }

  if (!disabled) {
    ipcMain.handle(PILLS_IPC.get, (e) => {
      if (!fromPills(e)) throw new Error('pills IPC from an unknown sender')
      return view
    })
    ipcMain.on(PILLS_IPC.open, (e, raw: unknown) => {
      const id = pillIdOf(raw)
      const item = id ? view.items.find((i) => i.id === id) : undefined
      if (!fromPills(e) || !item) return log('pills', 'ignored an open from an unknown sender or for an unknown pill')
      o.onOpen(item)
      if (item.phase === 'failed') model.dismiss(item.id) // a failure stays until it has been looked at
    })
    ipcMain.on(PILLS_IPC.stop, (e, raw: unknown) => {
      const id = pillIdOf(raw)
      const item = id ? view.items.find((i) => i.id === id) : undefined
      if (!fromPills(e) || !item || !item.stoppable) return log('pills', 'ignored a stop from an unknown sender or for a pill that cannot be stopped')
      o.onStop(item.id)
    })
    ipcMain.on(PILLS_IPC.size, (e, raw: unknown) => {
      const h = pillsWindowHeight(raw)
      if (!fromPills(e) || h === null) return
      height = h
      place()
    })
  }

  return {
    view: () => view,
    window: () => (alive() ? (win as BrowserWindow) : null),
    png: async () => (alive() ? (await (win as BrowserWindow).webContents.capturePage()).toPNG() : null),
    dispose() {
      off()
      model.dispose()
      if (!disabled) {
        screen.off('display-added', replace)
        screen.off('display-removed', replace)
        screen.off('display-metrics-changed', replace)
      }
      if (!disabled) {
        ipcMain.removeHandler(PILLS_IPC.get)
        ipcMain.removeAllListeners(PILLS_IPC.open)
        ipcMain.removeAllListeners(PILLS_IPC.stop)
        ipcMain.removeAllListeners(PILLS_IPC.size)
      }
      if (win && !win.isDestroyed()) win.destroy()
      win = null
    },
  }
}
