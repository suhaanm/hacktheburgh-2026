// The wire between main and the wake card page: channel names and types only, no Electron (the preload, the page and main import this).
// The page can ask for three things back, nothing else. Whether a click was a REAL mouse click is decided in the page (an event that the browser
// itself produced, from a mouse) and checked again in main (right sender, right card, not in the first 600 ms).

export const WAKE_CARD_IPC = {
  show: 'wake-card:show', // main -> page: the card to draw
  hide: 'wake-card:hide', // main -> page
  answer: 'wake-card:answer', // page -> main: a button was clicked
  esc: 'wake-card:esc', // page -> main: Escape (closes the card without an answer)
  size: 'wake-card:size', // page -> main: the card's measured size
} as const

export interface WakeCardView {
  id: string
  title: string
  body: string
  buttons: Array<{ id: string; label: string }>
}

export interface WakeCardAnswer {
  id: string
  buttonId: string
  /** True only for an event the browser produced from a real mouse click (isTrusted, a pointer of type mouse, detail of at least 1). */
  real: boolean
}

export interface WakeCardApi {
  onShow(cb: (v: WakeCardView) => void): () => void
  onHide(cb: () => void): () => void
  answer(a: WakeCardAnswer): void
  esc(id: string): void
  size(s: { w: number; h: number }): void
}

declare global {
  interface Window {
    knackWakeCard?: WakeCardApi
  }
}

/** The one definition of "a real mouse click" the page uses: produced by the browser, from a mouse, with a click count. A key press that
 *  activates a focused button, a script's `.click()` or a synthetic event fails this. */
export function isRealMouseClick(e: { isTrusted: boolean; detail: number; pointerType?: string; button?: number }): boolean {
  return e.isTrusted === true && e.detail >= 1 && e.pointerType === 'mouse' && (e.button === undefined || e.button === 0)
}
