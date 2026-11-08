// The wake card window: an interim corner card (bottom-right of the work area, 16 px inset) that implements CardPort until the shell's corner
// column (docs/knack-ux/08-window-states.md) takes the port over. Made like the HUD and the Cue panel: a non-activating panel that never takes
// focus, always on top, hidden from screen capture (a model must not see its own consent card). One card at a time. It answers ONLY for a real
// mouse click (checked in the page and again here), ignores clicks for the first 600 ms after it appears, closes on Escape or on its timer, and
// reports Escape and the timer as "no answer".
import path from 'node:path'
import { BrowserWindow, ipcMain, screen } from 'electron'
import type { CardAnswer, CardPort, CardSpec } from './controller'
import { MISTAP_GUARD_MS, WAKE_CARD_IPC, cardBounds, type WakeCardAnswer, type WakeCardView } from './card-ipc'

const FOLLOW_MS = 500

export interface CardWindowOptions {
  /**
   * The bounds of the topmost other window in this corner (the Knack corner pill column, a permission card), or null. The card stacks above it instead of over it: the corner has one
   * place for each thing, bottom up, never overlapping. Absent: the card sits in the corner as before.
   */
  above?: () => { x: number; y: number; width: number; height: number } | null
  disabled?: boolean
  capturable?: boolean
  now?: () => number
  log?: (scope: string, ...args: unknown[]) => void
}

export interface CardWindow extends CardPort {
  window(): BrowserWindow | null
  dispose(): void
}

export function createCardWindow(o: CardWindowOptions = {}): CardWindow {
  const env = process.env
  const disabled = o.disabled ?? (env.ALONGSIDE_HEADLESS === '1' || env.ALONGSIDE_NO_OVERLAY === '1')
  const capturable = o.capturable ?? env.ALONGSIDE_OVERLAY_CAPTURABLE === '1'
  const now = o.now ?? Date.now
  const log = o.log ?? (() => undefined)

  let win: BrowserWindow | null = null
  let loaded = false
  let pending: { spec: CardSpec; resolve: (a: CardAnswer | null) => void; shownAt: number; timer: ReturnType<typeof setTimeout> } | null = null
  let size = { w: 348, h: 150 }
  let follow: ReturnType<typeof setInterval> | null = null

  const alive = (): boolean => win !== null && !win.isDestroyed() && !win.webContents.isDestroyed()
  const fromCard = (e: { sender: { id: number } }): boolean => alive() && e.sender.id === (win as BrowserWindow).webContents.id

  const place = (): void => {
    if (!alive()) return
    // The display that holds the pointer (where the worker is looking), not always the primary one.
    let wa = screen.getPrimaryDisplay().workArea
    try {
      wa = screen.getDisplayNearestPoint(screen.getCursorScreenPoint()).workArea
    } catch {
      /* no pointer position: the primary display */
    }
    ;(win as BrowserWindow).setBounds(cardBounds(wa, size, undefined, o.above?.() ?? null))
  }

  const settle = (answer: CardAnswer | null): void => {
    const p = pending
    if (!p) return
    pending = null
    clearTimeout(p.timer)
    if (follow) clearInterval(follow)
    follow = null
    if (alive()) {
      ;(win as BrowserWindow).webContents.send(WAKE_CARD_IPC.hide)
      ;(win as BrowserWindow).hide()
    }
    p.resolve(answer)
  }

  const ensure = (): void => {
    if (win || disabled) return
    const w = new BrowserWindow({
      width: size.w,
      height: size.h,
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
      focusable: false, // never steals the keyboard from the app the worker is in
      skipTaskbar: true,
      alwaysOnTop: true,
      ...(process.platform === 'darwin' ? { type: 'panel' as const } : {}),
      title: 'Knack',
      webPreferences: { preload: path.join(__dirname, '../preload/wakeCard.js'), contextIsolation: true, sandbox: true, nodeIntegration: false, backgroundThrottling: false },
    })
    win = w
    w.setAlwaysOnTop(true, 'screen-saver', 2)
    w.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true, skipTransformProcessType: true })
    w.setContentProtection(!capturable)
    w.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))
    w.webContents.on('will-navigate', (event) => event.preventDefault())
    w.webContents.on('did-finish-load', () => {
      loaded = true
      if (pending) send(pending.spec)
    })
    w.on('closed', () => {
      win = null
      loaded = false
      settle(null)
    })
    const devUrl = env.ELECTRON_RENDERER_URL
    if (devUrl) void w.loadURL(`${devUrl}/hey-card/index.html`)
    else void w.loadFile(path.join(__dirname, '../renderer/hey-card/index.html'))
  }

  const send = (spec: CardSpec): void => {
    if (!alive() || !loaded) return
    const view: WakeCardView = { id: spec.id, title: spec.title, body: spec.body, buttons: spec.buttons.map((b) => ({ id: b.id, label: b.label })) }
    ;(win as BrowserWindow).webContents.send(WAKE_CARD_IPC.show, view)
  }

  if (!disabled) {
    ipcMain.on(WAKE_CARD_IPC.size, (e, raw: unknown) => {
      if (!fromCard(e) || typeof raw !== 'object' || raw === null) return
      const r = raw as { w?: unknown; h?: unknown }
      if (typeof r.w !== 'number' || typeof r.h !== 'number' || !(r.w > 0 && r.w <= 600) || !(r.h > 0 && r.h <= 400)) return
      size = { w: Math.ceil(r.w), h: Math.ceil(r.h) }
      place()
      if (pending && alive() && !(win as BrowserWindow).isVisible()) (win as BrowserWindow).showInactive()
    })
    ipcMain.on(WAKE_CARD_IPC.answer, (e, raw: unknown) => {
      if (!fromCard(e) || !pending) return log('wake', 'ignored a card answer from an unknown sender or with no card')
      const a = raw as Partial<WakeCardAnswer> | null
      if (!a || a.id !== pending.spec.id || typeof a.buttonId !== 'string' || !pending.spec.buttons.some((b) => b.id === a.buttonId)) return
      if (now() - pending.shownAt < MISTAP_GUARD_MS) return // a mis-click guard
      // A card answers only for a real mouse click. A key or a script that activates a button is not an answer: the card stays.
      if (a.real !== true) return log('wake', 'ignored a card answer that was not a real mouse click')
      settle({ buttonId: a.buttonId, via: 'mouse' })
    })
    ipcMain.on(WAKE_CARD_IPC.esc, (e, id: unknown) => {
      if (fromCard(e) && pending && id === pending.spec.id) settle(null)
    })
  }

  return {
    ask(spec) {
      if (disabled) return Promise.resolve(null)
      settle(null) // one card at a time
      ensure()
      return new Promise<CardAnswer | null>((resolve) => {
        pending = { spec, resolve, shownAt: now(), timer: setTimeout(() => settle(null), Math.max(1000, spec.expireMs)) }
        send(spec)
        // The corner column below may appear, grow or go while the card waits: keep clear of it.
        if (o.above && !follow) follow = setInterval(place, FOLLOW_MS)
      })
    },
    close(id) {
      if (pending?.spec.id === id) settle(null)
    },
    window: () => (alive() ? win : null),
    dispose() {
      settle(null)
      if (!disabled) {
        ipcMain.removeAllListeners(WAKE_CARD_IPC.size)
        ipcMain.removeAllListeners(WAKE_CARD_IPC.answer)
        ipcMain.removeAllListeners(WAKE_CARD_IPC.esc)
      }
      if (alive()) (win as BrowserWindow).destroy()
      win = null
    },
  }
}
