// The HUD window: the kill switch pill (always reachable) and the proposal toast. A small frameless panel at the bottom-left of
// the work area, above the overlay, never takes focus, hidden from screen capture (the model must not see its own controls).
// It has its own preload (src/preload/hud.ts) and three IPC channels; the sender is checked on every message.
import path from 'node:path'
import { BrowserWindow, ipcMain, screen } from 'electron'
import { HUD_IPC } from '../shared/hud'
import type { HudModel } from './hud-model'
import { hudBounds } from './hud-model'

export interface HudDeps {
  model: HudModel
  log: (scope: string, ...args: unknown[]) => void
  disabled?: boolean // ALONGSIDE_HEADLESS / ALONGSIDE_NO_OVERLAY
  capturable?: boolean // ALONGSIDE_OVERLAY_CAPTURABLE=1 (demo recording)
}

export interface HudHandle {
  // Send the model's current state to the page (the model calls this through its push callback).
  push(): void
  window(): BrowserWindow | null
  png(): Promise<Buffer | null>
  // Dev surface only: show the hovered look of the Stop pill without a pointer (for looking at it).
  preview(mode: 'hover' | 'none'): Promise<void>
  dispose(): void
}

const MIN = { width: 120, height: 40 }
const MAX_HEIGHT = 520

export function registerHud(deps: HudDeps): HudHandle {
  const env = process.env
  const disabled = deps.disabled ?? (env.ALONGSIDE_HEADLESS === '1' || env.ALONGSIDE_NO_OVERLAY === '1')
  if (disabled) return { push: () => undefined, window: () => null, png: async () => null, preview: async () => undefined, dispose: () => undefined }
  const capturable = deps.capturable ?? env.ALONGSIDE_OVERLAY_CAPTURABLE === '1'

  const wa = () => screen.getPrimaryDisplay().workArea
  const win = new BrowserWindow({
    ...hudBounds(wa(), MIN),
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
    focusable: false, // never steals focus from the app the person is working in
    skipTaskbar: true,
    alwaysOnTop: true,
    ...(process.platform === 'darwin' ? { type: 'panel' as const } : {}),
    title: 'Understudy',
    webPreferences: { preload: path.join(__dirname, '../preload/hud.js'), contextIsolation: true, sandbox: true, nodeIntegration: false, backgroundThrottling: false },
  })
  win.setAlwaysOnTop(true, 'screen-saver', 2)
  win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true, skipTransformProcessType: true })
  win.setContentProtection(!capturable)
  win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))
  win.webContents.on('will-navigate', (event) => event.preventDefault())

  const alive = () => !win.isDestroyed() && !win.webContents.isDestroyed()
  const fromHud = (event: { sender: { id: number } }): boolean => alive() && event.sender.id === win.webContents.id

  // The page's own height drives the window (same trick as the toast: no extra IPC).
  const fit = (): void => {
    if (!alive()) return
    void win.webContents
      .executeJavaScript(`(() => { const c = document.querySelector('[data-hud-card]'); if (!c) return null; const r = c.getBoundingClientRect(); return { w: Math.ceil(r.width), h: Math.ceil(r.height) } })()`)
      .then((size: { w: number; h: number } | null) => {
        if (!alive() || !size) return
        win.setBounds(hudBounds(wa(), { width: Math.max(MIN.width, size.w + 6), height: Math.min(MAX_HEIGHT, Math.max(MIN.height, size.h + 6)) }))
      })
      .catch(() => undefined)
  }
  const push = (): void => {
    if (!alive()) return
    win.webContents.send(HUD_IPC.state, deps.model.state())
    for (const ms of [30, 140, 400]) setTimeout(fit, ms)
  }

  ipcMain.handle(HUD_IPC.get, (event) => {
    if (!fromHud(event)) throw new Error('HUD IPC from an unknown sender')
    return deps.model.state()
  })
  ipcMain.on(HUD_IPC.action, (event, raw: unknown) => {
    if (!fromHud(event)) {
      deps.log('hud', 'ignored an action from an unknown sender')
      return
    }
    deps.model.handle(raw)
  })

  const devUrl = process.env.ELECTRON_RENDERER_URL
  if (devUrl) void win.loadURL(`${devUrl}/hud/index.html`)
  else void win.loadFile(path.join(__dirname, '../renderer/hud/index.html'))
  win.webContents.on('did-finish-load', () => {
    push()
    win.showInactive()
  })

  return {
    push,
    window: () => (alive() ? win : null),
    png: async () => (alive() ? (await win.webContents.capturePage()).toPNG() : null),
    preview: async (mode) => {
      if (alive()) await win.webContents.executeJavaScript(`document.documentElement.dataset.preview = ${JSON.stringify(mode)}`, true)
    },
    dispose() {
      ipcMain.removeHandler(HUD_IPC.get)
      ipcMain.removeAllListeners(HUD_IPC.action)
      if (!win.isDestroyed()) win.destroy()
    },
  }
}
