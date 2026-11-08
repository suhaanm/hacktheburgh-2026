// The Ask bar's small shared surface: its channels, its geometry, the cleaning of what is typed, and the one fixed sentence it says when typing cannot be answered.
// Pure, so the window (ask-bar.ts), the preload and the page can all use it and the tests can reach it without Electron.

export const ASK_IPC = {
  open: 'ask:open', // main -> page: the bar opened (with a prefilled phrase, or empty), or closed (the page clears itself)
  submit: 'ask:submit', // page -> main (invoke): the typed line; answers { ok, line? }
  close: 'ask:close', // page -> main: Escape
  size: 'ask:size', // page -> main: the card's height, so the window fits it
} as const

export interface AskSubmitResult {
  /** The line was taken (the bar closes). */
  ok: boolean
  /** When it was not: one plain sentence to show under the input. */
  line?: string
}

export interface AskApi {
  onOpen(cb: (o: { prefill: string; closed?: boolean }) => void): () => void
  submit(text: string): Promise<AskSubmitResult>
  close(): void
  size(height: number): void
}

declare global {
  interface Window {
    knackAsk?: AskApi
  }
}

/** The card, per docs/knack-ux/08-window-states.md: 560 by 64, centred, in the upper third. The window adds room for the shadow all round. */
export const ASK_CARD = { width: 560, height: 64 } as const
export const ASK_PAD = 8
export const ASK_MAX_HEIGHT = 168
export const ASK_MAX_TEXT = 500

export interface Rect {
  x: number
  y: number
  width: number
  height: number
}

/** The window's bounds: centred across the work area, its card's top a fifth of the way down (the upper third), `height` being the card's height plus the padding. */
export function askBarBounds(workArea: Rect, windowHeight: number): Rect {
  const width = ASK_CARD.width + 2 * ASK_PAD
  return { x: Math.round(workArea.x + (workArea.width - width) / 2), y: Math.round(workArea.y + workArea.height * 0.2) - ASK_PAD, width, height: windowHeight }
}

/** The height the window needs for a card of this height, kept inside the limits the page may ask for. */
export function askWindowHeight(cardHeight: unknown): number | null {
  if (typeof cardHeight !== 'number' || !Number.isFinite(cardHeight)) return null
  const h = Math.ceil(cardHeight)
  if (h < ASK_CARD.height || h > ASK_MAX_HEIGHT) return null
  return h + 2 * ASK_PAD
}

/** What was typed, as one clean line (or null when there is nothing to send): a string, line breaks and runs of spaces flattened, trimmed, and cut at the limit. */
export function cleanAsk(raw: unknown): string | null {
  if (typeof raw !== 'string') return null
  const one = raw.replace(/\s+/g, ' ').trim()
  return one.length === 0 ? null : one.slice(0, ASK_MAX_TEXT)
}

/** The talk key as people say it: Alt is Option and CommandOrControl is Command on a Mac. */
export function keyLabel(accelerator: string): string {
  return accelerator
    .split('+')
    .map((k) => ({ Alt: 'Option', Option: 'Option', CommandOrControl: 'Command', CmdOrCtrl: 'Command', Command: 'Command', Cmd: 'Command', Control: 'Control', Ctrl: 'Control', Shift: 'Shift' })[k] ?? k)
    .join('-')
}

/** The one sentence the bar says when a typed line cannot be answered (typed chat has no model behind it in this build): plain, and it says what to do. */
export function askUnavailableLine(talkKey: string): string {
  return `Typing is not on yet. Hold ${keyLabel(talkKey)} and speak.`
}
