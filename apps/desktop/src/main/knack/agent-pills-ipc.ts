// The background agent pills' small shared surface: their channels, their geometry, and the checks on what the page may send. Pure, so the window, the preload, the page and the
// tests share it without Electron.
import type { PillsView } from './agent-pills-model'

export const PILLS_IPC = {
  get: 'pills:get', // page -> main (invoke): the current view
  state: 'pills:state', // main -> page: the view changed
  open: 'pills:open', // page -> main: a pill was clicked (its id)
  stop: 'pills:stop', // page -> main: the stop button of a pill (its id)
  size: 'pills:size', // page -> main: the column's height, so the window fits it
} as const

export interface PillsApi {
  get(): Promise<PillsView>
  onState(cb: (v: PillsView) => void): () => void
  open(id: string): void
  stop(id: string): void
  size(height: number): void
}

declare global {
  interface Window {
    knackPills?: PillsApi
  }
}

export interface Rect {
  x: number
  y: number
  width: number
  height: number
}

/** The column's window: 16 px in from the right edge and 16 px below the top of the work area (which starts under the menu bar, so the menu bar is never covered). */
export const PILLS_INSET = 16
export const PILLS_WIDTH = 288
export const PILLS_PAD = 3 // room for the shadow inside the window
export const PILLS_MAX_HEIGHT = 320

export function pillsBounds(workArea: Rect, height: number): Rect {
  return { x: workArea.x + workArea.width - PILLS_WIDTH - PILLS_INSET + PILLS_PAD, y: workArea.y + PILLS_INSET - PILLS_PAD, width: PILLS_WIDTH, height }
}

/** The height the page may ask for, or null. */
export function pillsWindowHeight(raw: unknown): number | null {
  if (typeof raw !== 'number' || !Number.isFinite(raw) || raw < 1 || raw > PILLS_MAX_HEIGHT) return null
  return Math.ceil(raw)
}

/** A task id or run id from the page: only the two shapes the service makes (tk_ and r_ followed by letters and digits), else null. */
export function pillIdOf(raw: unknown): string | null {
  return typeof raw === 'string' && /^(tk|r)_[A-Za-z0-9]{3,24}$/.test(raw) ? raw : null
}
