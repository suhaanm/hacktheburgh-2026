// Adapted from farzaa/clicky (MIT) — leanring-buddy/OverlayWindow.swift (click-through, screen-saver level, all Spaces, over full-screen apps)
// Everything about the overlay BrowserWindow that capture cares about, in one place.
// Empirical result (docs/OVERLAY_NOTES.md): on macOS 26.2 + Electron 45, setContentProtection(true) excludes the
// overlay from desktopCapturer, so grounding/verify shots are clean without hiding anything. It also hides the
// overlay from QuickTime/OBS/screenshots, so ALONGSIDE_OVERLAY_CAPTURABLE=1 turns protection off for demo
// recording; capture then falls back to hiding the overlay (opacity 0) around ground/verify grabs.
import type { BrowserWindow } from 'electron'

let overlay: BrowserWindow | null = null
let protectedFromCapture = false

export const overlayCapturable = (): boolean => process.env.ALONGSIDE_OVERLAY_CAPTURABLE === '1'

export function isOverlayProtected(): boolean {
  return protectedFromCapture
}

// Called once by windows.ts right after creating the overlay window. Idempotent.
export function configureOverlayWindow(win: BrowserWindow): void {
  overlay = win
  win.setIgnoreMouseEvents(true)
  win.setAlwaysOnTop(true, 'screen-saver')
  win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true, skipTransformProcessType: true })
  protectedFromCapture = !overlayCapturable()
  win.setContentProtection(protectedFromCapture)

  // Lazy so unit tests that import this file without Electron keep working.
  void import('electron').then(({ screen }) => {
    const refit = (): void => {
      if (win.isDestroyed()) return
      win.setBounds(screen.getPrimaryDisplay().bounds)
    }
    screen.on('display-metrics-changed', refit)
    screen.on('display-added', refit)
    screen.on('display-removed', refit)
    win.once('closed', () => {
      screen.off('display-metrics-changed', refit)
      screen.off('display-added', refit)
      screen.off('display-removed', refit)
      if (overlay === win) overlay = null
    })
    refit()
  })
}

// Runs `fn` with the overlay invisible when it would otherwise be captured. Returns whether it was hidden.
export async function withOverlayHidden<T>(needed: boolean, fn: () => Promise<T>): Promise<{ value: T; hidden: boolean }> {
  const win = overlay
  if (!needed || protectedFromCapture || !win || win.isDestroyed() || !win.isVisible()) return { value: await fn(), hidden: false }
  win.setOpacity(0)
  try {
    // One frame for the compositor; measured: opacity 0 is already honoured by the next capture.
    await new Promise((r) => setTimeout(r, 16))
    return { value: await fn(), hidden: true }
  } finally {
    if (!win.isDestroyed()) win.setOpacity(1)
  }
}
