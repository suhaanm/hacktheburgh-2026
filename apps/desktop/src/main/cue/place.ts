// Where the Cue panel (the chip, the question card, the offer) goes on the screen. Pure geometry in screen DIPs, no Electron.
// Rules: always inside the work area (never under the menu bar or the Dock), never over the target, near it. The edge of the panel that
// faces the target stays put when the panel changes size (card -> chip), so the content grows away from the target instead of jumping.
import { CUE_TOKENS } from './tokens'

export interface Rect {
  x: number
  y: number
  w: number
  h: number
}
export interface Pt {
  x: number
  y: number
}
export type Side = 'right' | 'below' | 'above' | 'left' | 'near' | 'corner'

export interface PlaceOptions {
  // Order to try the sides in. The chip prefers below, the card prefers right.
  prefer?: readonly Side[]
  gap?: number
  margin?: number
  // With no target: put the panel near this point (the cursor, where the worker is stuck).
  anchorPoint?: Pt | null
  // Other things to keep clear of (the ghost cursor's landing, another window of ours).
  avoid?: readonly Rect[]
}

export const CHIP_SIDES: readonly Side[] = ['below', 'right', 'above', 'left']
export const CARD_SIDES: readonly Side[] = ['right', 'below', 'left', 'above']

const right = (r: Rect): number => r.x + r.w
const bottom = (r: Rect): number => r.y + r.h
const clamp = (v: number, lo: number, hi: number): number => Math.min(Math.max(v, lo), Math.max(lo, hi))

export function overlapArea(a: Rect, b: Rect): number {
  const w = Math.min(right(a), right(b)) - Math.max(a.x, b.x)
  const h = Math.min(bottom(a), bottom(b)) - Math.max(a.y, b.y)
  return w > 0 && h > 0 ? w * h : 0
}

const inflate = (r: Rect, by: number): Rect => ({ x: r.x - by, y: r.y - by, w: r.w + 2 * by, h: r.h + 2 * by })
const inside = (r: Rect, area: Rect): boolean => r.x >= area.x - 0.01 && r.y >= area.y - 0.01 && right(r) <= right(area) + 0.01 && bottom(r) <= bottom(area) + 0.01

/** Norm 0..1000 box -> display DIPs (the display's full bounds, the same mapping the overlay uses). */
export function normBoxToRect(b: { xmin: number; ymin: number; xmax: number; ymax: number }, display: Rect): Rect {
  return { x: display.x + (b.xmin / 1000) * display.w, y: display.y + (b.ymin / 1000) * display.h, w: ((b.xmax - b.xmin) / 1000) * display.w, h: ((b.ymax - b.ymin) / 1000) * display.h }
}

export function placePanel(size: { w: number; h: number }, target: Rect | null, work: Rect, o: PlaceOptions = {}): { rect: Rect; side: Side } {
  const margin = o.margin ?? CUE_TOKENS.placement.margin
  const gap = o.gap ?? CUE_TOKENS.chip.gap
  const safe = inflate(work, -margin)
  const avoid = o.avoid ?? []
  const make = (x: number, y: number): Rect => ({ x, y, w: size.w, h: size.h })
  const clearOf = (r: Rect): boolean => (target ? overlapArea(r, inflate(target, gap * 0.6)) === 0 : true) && avoid.every((a) => overlapArea(r, a) === 0)

  if (target) {
    const sides = o.prefer ?? CHIP_SIDES
    const candidate = (side: Side): Rect | null => {
      switch (side) {
        case 'below':
          return make(clamp(target.x, safe.x, right(safe) - size.w), bottom(target) + gap)
        case 'above':
          return make(clamp(target.x, safe.x, right(safe) - size.w), target.y - gap - size.h)
        case 'right':
          return make(right(target) + gap, clamp(target.y, safe.y, bottom(safe) - size.h))
        case 'left':
          return make(target.x - gap - size.w, clamp(target.y, safe.y, bottom(safe) - size.h))
        default:
          return null
      }
    }
    for (const side of sides) {
      const r = candidate(side)
      if (r && inside(r, safe) && clearOf(r)) return { rect: r, side }
    }
    // Nothing next to the target fits: the free corner of the work area farthest from it.
    const corners = [make(safe.x, safe.y), make(right(safe) - size.w, safe.y), make(safe.x, bottom(safe) - size.h), make(right(safe) - size.w, bottom(safe) - size.h)]
    const tc: Pt = { x: target.x + target.w / 2, y: target.y + target.h / 2 }
    const ranked = corners
      .map((r) => ({ r, overlap: overlapArea(r, target) + avoid.reduce((s, a) => s + overlapArea(r, a), 0), dist: Math.hypot(r.x + r.w / 2 - tc.x, r.y + r.h / 2 - tc.y) }))
      .sort((a, b) => a.overlap - b.overlap || b.dist - a.dist)
    return { rect: ranked[0].r, side: 'corner' }
  }

  const pt = o.anchorPoint
  if (pt) {
    // Near the point, below and to the right of it, so the worker's eyes (and the cursor) are not covered.
    const near = make(clamp(pt.x + 18, safe.x, right(safe) - size.w), clamp(pt.y + 22, safe.y, bottom(safe) - size.h))
    if (overlapArea(near, { x: pt.x - 6, y: pt.y - 6, w: 12, h: 12 }) === 0 && clearOf(near)) return { rect: near, side: 'near' }
    const above = make(clamp(pt.x + 18, safe.x, right(safe) - size.w), clamp(pt.y - 22 - size.h, safe.y, bottom(safe) - size.h))
    return { rect: above, side: 'near' }
  }
  // Nothing to be near: bottom right of the work area, above the Dock.
  return { rect: make(right(safe) - size.w, bottom(safe) - size.h), side: 'corner' }
}

// The panel window is its content plus room for the shadow. The content, not the window, is what keeps its distance from the target.
export const PANEL_PAD = 6

/** Places the window of a panel whose window size (content plus padding) is `size`; the returned rect is the window, the content sits PANEL_PAD inside. */
export function placeWindow(size: { w: number; h: number }, target: Rect | null, work: Rect, o: PlaceOptions = {}): { rect: Rect; side: Side } {
  const inner = { w: Math.max(0, size.w - 2 * PANEL_PAD), h: Math.max(0, size.h - 2 * PANEL_PAD) }
  const placed = placePanel(inner, target, work, o)
  return { side: placed.side, rect: { x: placed.rect.x - PANEL_PAD, y: placed.rect.y - PANEL_PAD, w: size.w, h: size.h } }
}
