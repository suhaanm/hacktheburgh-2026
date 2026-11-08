// The Ask bar: a small centred input that opens on an Option-Space tap (or the menu bar's "Ask Knack…"), takes one line, and closes on Return, Escape or when it loses focus
// (docs/knack-ux/08-window-states.md: a separate window, 560 by 64, upper third, closes on blur or Esc). Made like the other small windows: frameless, transparent, always on
// top on every Space, hidden from screen capture (a model must not see what the worker is typing), and it answers only for its own page. Unlike the corner cards it takes the
// keyboard when it opens (it is a panel, so Knack does not come to the front with it) and gives it back when it closes.
//
// What happens to the line is decided by `submit` (the shell wires it): in this build typed chat has no model behind it, so a line goes only into a voice conversation that is
// already open; otherwise the bar says one plain sentence and stays, so nothing is lost and nothing pretends to work.
import path from 'node:path'
import { BrowserWindow, ipcMain, screen } from 'electron'
import { ASK_CARD, ASK_IPC, ASK_PAD, askBarBounds, askWindowHeight, cleanAsk, type AskSubmitResult } from './ask-ipc'

/** A blur in the first moments after opening is the system settling focus, not the worker leaving: it must not close the bar. */
export const BLUR_GRACE_MS = 300

export interface AskBarOptions {
  /** Takes a cleaned line; ok: the line went somewhere (the bar closes), else one sentence to show. */
  submit: (text: string) => Promise<AskSubmitResult> | AskSubmitResult
  onOpened?: () => void
  onClosed?: () => void
  /** The window is built and works but is never shown (the hidden check). */
  hidden?: boolean
  disabled?: boolean
  capturable?: boolean
  now?: () => number
  log?: (scope: string, ...args: unknown[]) => void
}

export interface AskBar {
  open(prefill?: string): void
  close(): void
  isOpen(): boolean
  window(): BrowserWindow | null
  png(): Promise<Buffer | null>
  dispose(): void
}

export function createAskBar(o: AskBarOptions): AskBar {
  const env = process.env
  const disabled = o.disabled ?? (env.ALONGSIDE_HEADLESS === '1' || env.ALONGSIDE_NO_OVERLAY === '1')
  const capturable = o.capturable ?? env.ALONGSIDE_OVERLAY_CAPTURABLE === '1'
  const now = o.now ?? Date.now
  const log = o.log ?? (() => undefined)

  let win: BrowserWindow | null = null
  let loaded = false
  let open = false
  let openedAt = 0
  let prefill = ''
  let windowHeight = ASK_CARD.height + 2 * ASK_PAD
  let displayId: number | null = null

  const alive = (): boolean => win !== null && !win.isDestroyed() && !win.webContents.isDestroyed()
  const fromBar = (e: { sender: { id: number } }): boolean => alive() && e.sender.id === (win as BrowserWindow).webContents.id

  /** The display holding the pointer when the bar opens (it stays there while open). */
  const workArea = () => {
    const all = screen.getAllDisplays()
    const found = displayId !== null ? all.find((d) => d.id === displayId) : undefined
    const chosen = found ?? screen.getDisplayNearestPoint(screen.getCursorScreenPoint())
    displayId = chosen.id
    return chosen.workArea
  }
  const place = (): void => {
    if (alive()) (win as BrowserWindow).setBounds(askBarBounds(workArea(), windowHeight))
  }

  const send = (): void => {
    if (alive() && loaded) (win as BrowserWindow).webContents.send(ASK_IPC.open, { prefill })
  }

  const ensure = (): void => {
    if (win || disabled) return
    const first = askBarBounds({ x: 0, y: 0, width: 1440, height: 900 }, windowHeight)
    const w = new BrowserWindow({
      width: first.width,
      height: first.height,
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
      focusable: true, // it takes the keyboard to type into
      skipTaskbar: true,
      alwaysOnTop: true,
      ...(process.platform === 'darwin' ? { type: 'panel' as const } : {}),
      title: 'Ask Knack',
      webPreferences: { preload: path.join(__dirname, '../preload/ask.js'), contextIsolation: true, sandbox: true, nodeIntegration: false, backgroundThrottling: false },
    })
    win = w
    w.setAlwaysOnTop(true, 'screen-saver', 3)
    w.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true, skipTransformProcessType: true })
    w.setContentProtection(!capturable)
    w.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))
    w.webContents.on('will-navigate', (event) => event.preventDefault())
    w.webContents.on('did-finish-load', () => {
      loaded = true
      if (open) send()
    })
    w.on('blur', () => {
      if (open && now() - openedAt > BLUR_GRACE_MS) api.close()
    })
    w.on('closed', () => {
      win = null
      loaded = false
      if (open) {
        open = false
        o.onClosed?.()
      }
    })
    const devUrl = env.ELECTRON_RENDERER_URL
    if (devUrl) void w.loadURL(`${devUrl}/ask/index.html`)
    else void w.loadFile(path.join(__dirname, '../renderer/ask/index.html'))
  }

  if (!disabled) {
    ipcMain.handle(ASK_IPC.submit, async (e, raw: unknown): Promise<AskSubmitResult> => {
      if (!fromBar(e) || !open) throw new Error('ask IPC from an unknown sender')
      const text = cleanAsk(raw)
      if (text === null) return { ok: false }
      let result: AskSubmitResult
      try {
        result = await o.submit(text)
      } catch (err) {
        log('ask', 'submit failed:', err instanceof Error ? err.message : String(err))
        result = { ok: false, line: 'Something went wrong. Try again.' }
      }
      if (result.ok) api.close()
      return result
    })
    ipcMain.on(ASK_IPC.close, (e) => {
      if (fromBar(e)) api.close()
    })
    ipcMain.on(ASK_IPC.size, (e, raw: unknown) => {
      if (!fromBar(e)) return
      const h = askWindowHeight(raw)
      if (h === null) return
      windowHeight = h
      if (open) place()
    })
  }

  const api: AskBar = {
    open(text = '') {
      if (disabled) return
      ensure()
      prefill = cleanAsk(text) ?? ''
      windowHeight = ASK_CARD.height + 2 * ASK_PAD
      displayId = null
      open = true
      openedAt = now()
      place()
      if (alive() && !o.hidden) {
        ;(win as BrowserWindow).show()
        ;(win as BrowserWindow).focus()
      }
      send()
      o.onOpened?.()
    },
    close() {
      if (!open) return
      open = false
      if (alive()) {
        const w = win as BrowserWindow
        w.webContents.send(ASK_IPC.open, { prefill: '', closed: true })
        if (w.isVisible()) w.hide()
      }
      o.onClosed?.()
    },
    isOpen: () => open,
    window: () => (alive() ? (win as BrowserWindow) : null),
    png: async () => (alive() ? (await (win as BrowserWindow).webContents.capturePage()).toPNG() : null),
    dispose() {
      if (!disabled) {
        ipcMain.removeHandler(ASK_IPC.submit)
        ipcMain.removeAllListeners(ASK_IPC.close)
        ipcMain.removeAllListeners(ASK_IPC.size)
      }
      open = false
      if (win && !win.isDestroyed()) win.destroy()
      win = null
    },
  }
  return api
}
