import type { OverlayController } from '../../shared/contracts'

// "Try the ring": the first run shows the worker what the on-screen guide looks like, with no permission and no click. The page names a spot in its own window (CSS pixels), main
// turns it into the 0..1000 box the overlay draws on the display, and the ring and the ghost cursor stay for four seconds. Pure geometry here; the shell draws and clears.
export interface Rect {
  x: number
  y: number
  width: number
  height: number
}

/** How long the ring stays. */
export const TRY_RING_MS = 4000

/** A fixed spot when the page names none: a calm 240 by 72 box in the upper middle of the window's content. */
export function defaultSpot(content: Rect): Rect {
  const width = Math.min(240, content.width)
  const height = Math.min(72, content.height)
  return { x: Math.round((content.width - width) / 2), y: Math.round(content.height * 0.28), width, height }
}

export type RingBox = [number, number, number, number]
export type RingPlan = { ok: true; box: RingBox } | { ok: false; reason: 'bad_request' | 'other_display' }

const finite = (n: unknown): n is number => typeof n === 'number' && Number.isFinite(n)

/** The page's spot, kept only if it is a real box inside the window's content (CSS pixels), else null. */
export function cleanSpot(raw: unknown, content: Rect): Rect | null {
  if (raw === undefined || raw === null) return defaultSpot(content)
  if (typeof raw !== 'object') return null
  const r = raw as Record<string, unknown>
  if (!finite(r.x) || !finite(r.y) || !finite(r.width) || !finite(r.height)) return null
  if (r.width < 8 || r.height < 8 || r.x < 0 || r.y < 0 || r.x + r.width > content.width + 1 || r.y + r.height > content.height + 1) return null
  return { x: r.x, y: r.y, width: r.width, height: r.height }
}

/**
 * The box [y0, x0, y1, x1] on a 0..1000 grid over `display` (the display the overlay covers) for `spot` inside the window whose content sits at `content` on the screen. Not on that display:
 * no box (the ring would land in the wrong place).
 */
export function planRing(rawSpot: unknown, content: Rect, display: Rect): RingPlan {
  const spot = cleanSpot(rawSpot, content)
  if (!spot) return { ok: false, reason: 'bad_request' }
  const abs = { x: content.x + spot.x, y: content.y + spot.y, width: spot.width, height: spot.height }
  const cx = abs.x + abs.width / 2
  const cy = abs.y + abs.height / 2
  if (cx < display.x || cx > display.x + display.width || cy < display.y || cy > display.y + display.height) return { ok: false, reason: 'other_display' }
  const clamp = (v: number): number => Math.max(0, Math.min(1000, Math.round(v)))
  const x0 = clamp(((abs.x - display.x) / display.width) * 1000)
  const x1 = clamp(((abs.x + abs.width - display.x) / display.width) * 1000)
  const y0 = clamp(((abs.y - display.y) / display.height) * 1000)
  const y1 = clamp(((abs.y + abs.height - display.y) / display.height) * 1000)
  return { ok: true, box: [y0, x0, y1, x1] }
}

export interface TryRingTarget {
  show(box: RingBox, opts?: { ghost?: boolean }): void
  clear(): void
  displayBounds(): Rect
}
export type TryRingAnswer = { ok: true } | { ok: false; reason: 'bad_request' | 'not_ready' | 'window_hidden' | 'other_display' }

export interface TryRingDeps {
  /** The overlay's ring, or undefined while the app is still starting. */
  ring: () => TryRingTarget | undefined
  /** The Knack window now: whether it is up and in view, and where its page is on the screen. */
  window: () => { visible: boolean; minimised: boolean; content: Rect | null }
  setTimer?: (fn: () => void, ms: number) => unknown
  clearTimer?: (h: unknown) => void
}

/** The sample ring as the first run asks for it: draws, then takes itself away after four seconds (a second call moves it and starts the four seconds again). Never clicks. */
export function createTryRing(d: TryRingDeps): { run(raw: unknown): TryRingAnswer; stop(): void } {
  const setT = d.setTimer ?? ((fn, ms) => setTimeout(fn, ms))
  const clearT = d.clearTimer ?? ((h) => clearTimeout(h as ReturnType<typeof setTimeout>))
  let timer: unknown = null
  let shown: TryRingTarget | null = null
  const stop = (): void => {
    if (timer !== null) clearT(timer)
    timer = null
    shown?.clear()
    shown = null
  }
  return {
    run(raw) {
      const ring = d.ring()
      if (!ring) return { ok: false, reason: 'not_ready' }
      const w = d.window()
      if (!w.visible || w.minimised || !w.content) return { ok: false, reason: 'window_hidden' }
      const plan = planRing(raw, w.content, ring.displayBounds())
      if (!plan.ok) return plan
      if (timer !== null) clearT(timer)
      ring.show(plan.box, { ghost: true })
      shown = ring
      timer = setT(() => {
        timer = null
        shown?.clear()
        shown = null
      }, TRY_RING_MS)
      return { ok: true }
    },
    stop,
  }
}

export const TRY_RING_ID = 'point-try'
export const TRY_GHOST_ID = 'point-try-ghost'

/** The overlay's ring and ghost cursor for the sample: ids of their own, so a voice ring (point-voice) is never taken over. No label and no words on it. */
export function createTryRingPort(overlay: Pick<OverlayController, 'show' | 'clear'>, displayBounds: () => Rect) {
  return {
    show(box: RingBox, opts?: { ghost?: boolean }): void {
      const [y0, x0, y1, x1] = box
      const ring = { id: TRY_RING_ID, kind: 'ring' as const, tone: 'guide' as const, box: { xmin: x0, ymin: y0, xmax: x1, ymax: y1 }, exact: true }
      if (opts?.ghost) overlay.show([ring, { id: TRY_GHOST_ID, kind: 'ghostCursor', tone: 'guide', path: [{ x: (x0 + x1) / 2, y: (y0 + y1) / 2 }] }])
      else overlay.show([ring])
    },
    clear(): void {
      overlay.clear([TRY_RING_ID, TRY_GHOST_ID])
    },
    displayBounds,
  }
}
