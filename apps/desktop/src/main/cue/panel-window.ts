// The Cue panel window: the chip, the question card and the offer. One small frameless panel, made like the HUD's Stop pill: `type: 'panel'`
// on macOS (a non-activating panel), always on top, on every Space, hidden from screen capture (the model must not see its own prompt), and
// SHOWN WITHOUT FOCUS: it never takes the keyboard from the app the worker is in. A click on it gives it focus (then 1 to 4 and Escape work in
// the page); the global keys (keys.ts) work without it. It has its own preload and three IPC channels, and checks the sender on every message.
// Only created when the first cue is shown; hidden, not destroyed, between cues.
import path from 'node:path'
import { BrowserWindow, ipcMain, screen } from 'electron'
import { CueCardActionSchema, CueSizeSchema } from './action-schema'
import { createKeys, type ShortcutApi } from './keys'
import type { PanelPort } from './controller'
import { CUE_IPC, type CueCardAction, type CueView } from './ipc'
import { CARD_SIDES, CHIP_SIDES, normBoxToRect, placeWindow, type Pt, type Rect } from './place'
import { CUE_TOKENS } from './tokens'
import { WINDOW_TITLES } from '../../shared/brand'

export interface PanelWindowDeps {
  onAction(a: CueCardAction): void
  shortcuts: ShortcutApi
  // The page's visible text and controls as rectangles in screen DIPs (from the browser extension), or null when unknown.
  content?: () => Rect[] | null
  // Where the worker's pointer is, in screen DIPs (the card goes near it when there is no target).
  cursor?: () => Pt | null
  log?: (scope: string, ...args: unknown[]) => void
  // ALONGSIDE_HEADLESS / ALONGSIDE_NO_OVERLAY: no window at all.
  disabled?: boolean
  // ALONGSIDE_OVERLAY_CAPTURABLE=1 (demo recording): content protection off, exactly like the overlay.
  capturable?: boolean
}

export interface PanelWindow extends PanelPort {
  window(): BrowserWindow | null
  png(): Promise<Buffer | null>
}

const FIRST_SIZE = { w: 300, h: 60 }

export function createPanelWindow(deps: PanelWindowDeps): PanelWindow {
  const env = process.env
  const log = deps.log ?? (() => undefined)
  const disabled = deps.disabled ?? (env.ALONGSIDE_HEADLESS === '1' || env.ALONGSIDE_NO_OVERLAY === '1')
  const capturable = deps.capturable ?? env.ALONGSIDE_OVERLAY_CAPTURABLE === '1'

  let win: BrowserWindow | null = null
  let loaded = false
  let current: CueView = null
  let opts: { anchor: import('../../shared/protocol').NormBox | null; kind: 'chip' | 'card'; keep: boolean } = { anchor: null, kind: 'chip', keep: false }
  let size: { w: number; h: number } = FIRST_SIZE
  let pendingShow = false
  let showTimer: ReturnType<typeof setTimeout> | null = null
  let lastCard: Rect | null = null
  let hideTimer: ReturnType<typeof setTimeout> | null = null

  const alive = (): boolean => win !== null && !win.isDestroyed() && !win.webContents.isDestroyed()
  const live = (): BrowserWindow => win as BrowserWindow
  const fromPanel = (e: { sender: { id: number } }): boolean => alive() && e.sender.id === live().webContents.id

  const keys = createKeys(
    deps.shortcuts,
    {
      answer: (n) => {
        const v = current
        if (v?.mode === 'question' && v.options[n - 1]) deps.onAction({ type: 'answer', id: v.options[n - 1].id })
      },
      other: () => deps.onAction({ type: 'other' }),
      dismiss: () => deps.onAction({ type: 'dismiss' }),
    },
    log,
  )

  const place = (): void => {
    if (!alive() || !current) return
    const display = screen.getPrimaryDisplay()
    const card = opts.kind === 'card'
    let rect: Rect
    if (opts.keep && lastCard) {
      // The chip that is the card's collapsed answer stays where the card was.
      rect = { x: lastCard.x, y: lastCard.y, w: size.w, h: size.h }
    } else {
      const asRect = (r: { x: number; y: number; width: number; height: number }): Rect => ({ x: r.x, y: r.y, w: r.width, h: r.height })
      const target = opts.anchor ? normBoxToRect(opts.anchor, asRect(display.bounds)) : null
      rect = placeWindow(size, target, asRect(display.workArea), {
        kind: opts.kind,
        prefer: card ? CARD_SIDES : CHIP_SIDES,
        gap: card ? CUE_TOKENS.card.gap : CUE_TOKENS.chip.gap,
        anchorPoint: deps.cursor?.() ?? null,
        content: deps.content?.() ?? null,
      }).rect
    }
    if (card) lastCard = rect
    live().setBounds({ x: Math.round(rect.x), y: Math.round(rect.y), width: Math.round(rect.w), height: Math.round(rect.h) })
  }

  const ensure = (): void => {
    if (win || disabled) return
    const w = new BrowserWindow({
      width: FIRST_SIZE.w,
      height: FIRST_SIZE.h,
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
      // Focusable, so a click gives the page the keyboard; it is never shown with focus (showInactive below).
      focusable: true,
      ...(process.platform === 'darwin' ? { type: 'panel' as const } : {}),
      title: WINDOW_TITLES.cue,
      webPreferences: { preload: path.join(__dirname, '../preload/cue.js'), contextIsolation: true, sandbox: true, nodeIntegration: false, backgroundThrottling: false },
    })
    win = w
    w.setAlwaysOnTop(true, 'screen-saver', 1)
    w.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true, skipTransformProcessType: true })
    w.setContentProtection(!capturable)
    w.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))
    w.webContents.on('will-navigate', (event) => event.preventDefault())
    w.webContents.on('did-finish-load', () => {
      loaded = true
      if (current && alive()) w.webContents.send(CUE_IPC.view, current)
    })
    w.on('closed', () => {
      win = null
      loaded = false
    })
    const devUrl = env.ELECTRON_RENDERER_URL
    if (devUrl) void w.loadURL(`${devUrl}/cue/card/index.html`)
    else void w.loadFile(path.join(__dirname, '../renderer/cue/card/index.html'))
  }

  // Shown without focus, on top of the overlay.
  const reveal = (): void => {
    pendingShow = false
    if (showTimer) clearTimeout(showTimer)
    showTimer = null
    if (!alive() || !current) return
    place()
    live().showInactive() // (no moveTop: on a Mac it can bring a hidden window up with focus rules of its own)
  }

  const send = (): void => {
    if (alive() && loaded) live().webContents.send(CUE_IPC.view, current)
  }

  if (!disabled) {
    ipcMain.handle(CUE_IPC.get, (e) => {
      if (!fromPanel(e)) throw new Error('Cue IPC from an unknown sender')
      return current
    })
    ipcMain.on(CUE_IPC.action, (e, raw: unknown) => {
      if (!fromPanel(e)) return log('cue', 'ignored an action from an unknown sender')
      const parsed = CueCardActionSchema.safeParse(raw)
      if (!parsed.success) return log('cue', 'ignored a malformed action')
      deps.onAction(parsed.data)
    })
    ipcMain.on(CUE_IPC.size, (e, raw: unknown) => {
      if (!fromPanel(e)) return
      const parsed = CueSizeSchema.safeParse(raw)
      if (!parsed.success) return
      size = parsed.data
      place()
      // First size of a new cue: now it can be shown in the right place, without taking focus.
      if (pendingShow && alive() && current) reveal()
    })
  }

  return {
    set(view, o) {
      if (disabled) return
      current = view
      if (hideTimer) clearTimeout(hideTimer)
      hideTimer = null
      if (!view) {
        pendingShow = false
        if (showTimer) clearTimeout(showTimer)
        showTimer = null
        send() // the page fades its layers out
        hideTimer = setTimeout(() => {
          if (alive() && !current) live().hide()
        }, CUE_TOKENS.timing.crossfadeMs + 40)
        return
      }
      opts = o
      ensure()
      if (!alive()) return
      send()
      place()
      if (live().isVisible()) return
      // Hidden: show it once the page has said how big it is, so it never appears at the wrong size or in the wrong place; if the size does
      // not change (the same chip as last time) a short timer shows it anyway.
      pendingShow = true
      if (showTimer) clearTimeout(showTimer)
      showTimer = setTimeout(() => {
        if (pendingShow) reveal()
      }, 150)
    },
    keys: (o) => keys.set(o),
    window: () => (alive() ? win : null),
    png: async () => (alive() ? (await live().webContents.capturePage()).toPNG() : null),
    dispose() {
      keys.off()
      if (hideTimer) clearTimeout(hideTimer)
      if (showTimer) clearTimeout(showTimer)
      if (!disabled) {
        ipcMain.removeHandler(CUE_IPC.get)
        ipcMain.removeAllListeners(CUE_IPC.action)
        ipcMain.removeAllListeners(CUE_IPC.size)
      }
      if (alive()) live().destroy()
      win = null
    },
  }
}
