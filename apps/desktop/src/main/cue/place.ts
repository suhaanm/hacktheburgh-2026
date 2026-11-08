// Where the Cue panel (the chip, the question card, the offer) goes on the screen. Pure geometry in screen DIPs, no Electron.
// Rules, in this order:
//   1. Always inside the work area (never under the menu bar or the Dock), never over the target, never over anything in `avoid`.
//   2. Never over the page's own text and controls when there is free space. The page's content comes from the browser extension as plain
//      rectangles (no text); with it the panel goes to the free spot nearest the target. Without it (a native app, no extension) nothing is
//      known about the page, so the card docks at a predictable fixed place (a bottom corner above the Dock) and the chip sits beside the ring.
//   3. Near the target: the chip stays attached to the ring, sliding along its edge to find room; the card takes the nearest free spot anywhere.
// The edge of the panel that faces the target stays put when the panel changes size (card -> chip), so it grows away from the target.
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
export type PanelKind = 'chip' | 'card'

export interface PlaceOptions {
  kind?: PanelKind
  // Order to try the sides in. The chip prefers below, the card prefers right.
  prefer?: readonly Side[]
  gap?: number
  margin?: number
  // With no target: put the panel near this point (the cursor, where the worker is stuck).
  anchorPoint?: Pt | null
  // Other things to keep clear of, strictly (the ghost cursor's landing, another window of ours).
  avoid?: readonly Rect[]
  // The visible text and controls of the page, as rectangles. Null or empty: nothing is known about the page.
  content?: readonly Rect[] | null
}

export interface Placed {
  rect: Rect
  side: Side
  // Area (px squared) of page content the panel covers; 0 when it covers none, or when nothing is known.
  cover: number
  // With content known: is there ANY free spot for a panel this size? Null when content is not known.
  freeExists: boolean | null
}

export const CHIP_SIDES: readonly Side[] = ['below', 'right', 'above', 'left']
export const CARD_SIDES: readonly Side[] = ['right', 'below', 'left', 'above']

const right = (r: Rect): number => r.x + r.w
const bottom = (r: Rect): number => r.y + r.h
const clamp = (v: number, lo: number, hi: number): number => Math.min(Math.max(v, lo), Math.max(lo, hi))
const centre = (r: Rect): Pt => ({ x: r.x + r.w / 2, y: r.y + r.h / 2 })
const dist = (a: Pt, b: Pt): number => Math.hypot(a.x - b.x, a.y - b.y)

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

interface Cand {
  rect: Rect
  side: Side
  rank: number
  slide: number
}

const GRID = 12
const SLIDE = 8

function* span(from: number, to: number, step: number): Generator<number> {
  if (to < from) {
    yield from
    return
  }
  for (let v = from; v < to; v += step) yield v
  yield to
}

export function placePanel(size: { w: number; h: number }, target: Rect | null, work: Rect, o: PlaceOptions = {}): Placed {
  const kind: PanelKind = o.kind ?? 'chip'
  const margin = o.margin ?? CUE_TOKENS.placement.margin
  const gap = o.gap ?? (kind === 'card' ? CUE_TOKENS.card.gap : CUE_TOKENS.chip.gap)
  const safe = inflate(work, -margin)
  const avoid = o.avoid ?? []
  // The page's content with a little air around it: a panel is never tight against a line of text.
  const raw = (o.content ?? []).filter((c) => c.w > 0 && c.h > 0)
  const content = raw.map((c) => inflate(c, CUE_TOKENS.placement.contentAir))
  const known = content.length > 0
  // The same page without the air: the second choice, when no spot has air around the text but one still covers none of it.
  const tightCover = (r: Rect): number => raw.reduce((s, c) => s + overlapArea(r, c), 0)
  const make = (x: number, y: number): Rect => ({ x, y, w: size.w, h: size.h })
  const coverOf = (r: Rect): number => (known ? content.reduce((s, c) => s + overlapArea(r, c), 0) : 0)
  const clearOf = (r: Rect): boolean => (target ? overlapArea(r, inflate(target, gap * 0.6)) === 0 : true) && avoid.every((a) => overlapArea(r, a) === 0)
  const ok = (r: Rect): boolean => inside(r, safe) && clearOf(r)
  const done = (rect: Rect, side: Side, free: boolean | null): Placed => ({ rect, side, cover: Math.round(coverOf(rect)), freeExists: known ? free : null })

  // Is there any spot for a panel this size that covers no content and keeps clear of the target? (Only asked when content is known.)
  const gridCands = (): Cand[] => {
    const out: Cand[] = []
    for (const y of span(safe.y, bottom(safe) - size.h, GRID)) for (const x of span(safe.x, right(safe) - size.w, GRID)) out.push({ rect: make(x, y), side: 'near', rank: 9, slide: 0 })
    return out
  }
  const anyFree = (): boolean => known && gridCands().some((c) => ok(c.rect) && coverOf(c.rect) < 1)

  if (target) {
    const sides = o.prefer ?? (kind === 'card' ? CARD_SIDES : CHIP_SIDES)
    // Beside the target: aligned with it, or (when the page is known) slid along its edge to find room.
    const adjacent: Cand[] = []
    sides.forEach((side, rank) => {
      if (side === 'below' || side === 'above') {
        const y = side === 'below' ? bottom(target) + gap : target.y - gap - size.h
        const aligned = clamp(target.x, safe.x, right(safe) - size.w)
        adjacent.push({ rect: make(aligned, y), side, rank, slide: 0 })
        if (known) for (const x of span(clamp(target.x - size.w + 24, safe.x, right(safe) - size.w), clamp(right(target) - 24, safe.x, right(safe) - size.w), SLIDE)) adjacent.push({ rect: make(x, y), side, rank, slide: Math.abs(x - aligned) })
      } else if (side === 'right' || side === 'left') {
        const x = side === 'right' ? right(target) + gap : target.x - gap - size.w
        // Beside the target, a small chip is centred on it (a label for the ring); a taller panel starts level with its top.
        const aligned = clamp(kind === 'chip' ? target.y + (target.h - size.h) / 2 : target.y, safe.y, bottom(safe) - size.h)
        adjacent.push({ rect: make(x, aligned), side, rank, slide: 0 })
        if (known) for (const y of span(clamp(target.y - size.h + 12, safe.y, bottom(safe) - size.h), clamp(bottom(target) - 12, safe.y, bottom(safe) - size.h), SLIDE)) adjacent.push({ rect: make(x, y), side, rank, slide: Math.abs(y - aligned) })
      }
    })
    const pool = adjacent.filter((c) => ok(c.rect))
    const tc = centre(target)

    if (kind === 'chip') {
      // The chip stays attached to its ring. With the page known it takes the side and slide that cover the least; otherwise the first side that fits.
      if (pool.length > 0) {
        // The least content covered; then the least sliding (in 16 px steps, so a small slide does not beat a better side); then the side order.
        let best = known ? [...pool].sort((a, b) => Math.round(coverOf(a.rect)) - Math.round(coverOf(b.rect)) || Math.round(a.slide / 16) - Math.round(b.slide / 16) || a.rank - b.rank || a.slide - b.slide)[0] : pool[0]
        // Every spot touching the ring covers text: a free spot a little further out (still within a chip's reach of the ring) is better than covering it.
        if (known && coverOf(best.rect) >= 1) {
          const reach = inflate(target, CUE_TOKENS.placement.chipReach)
          const reachable = gridCands().filter((c) => ok(c.rect) && overlapArea(c.rect, reach) > 0)
          const aired = reachable.filter((c) => coverOf(c.rect) < 1)
          const near = aired.length > 0 ? aired : reachable.filter((c) => tightCover(c.rect) < 1)
          if (near.length > 0) {
            const free = near.sort((a, b) => dist(centre(a.rect), tc) - dist(centre(b.rect), tc) || a.rect.y - b.rect.y || a.rect.x - b.rect.x)[0]
            best = { rect: free.rect, side: 'near', rank: 9, slide: 0 }
          }
        }
        return done(best.rect, best.side, known ? anyFree() : null)
      }
    } else if (known) {
      // The card goes to the nearest spot that covers no content, anywhere; if there is none, the one that covers least.
      const all = [...pool, ...gridCands().filter((c) => ok(c.rect))]
      if (all.length > 0) {
        const byNearest = (a: Cand, b: Cand): number => dist(centre(a.rect), tc) - dist(centre(b.rect), tc) || a.rect.y - b.rect.y || a.rect.x - b.rect.x
        let best = [...all].sort((a, b) => Math.round(coverOf(a.rect)) - Math.round(coverOf(b.rect)) || byNearest(a, b))[0]
        // No spot with air around the text: one that still covers none of it is better than covering some.
        if (coverOf(best.rect) >= 1) {
          const tight = all.filter((c) => tightCover(c.rect) < 1).sort(byNearest)
          if (tight.length > 0) best = tight[0]
        }
        return done(best.rect, best.side, coverOf(best.rect) < 1 || tightCover(best.rect) < 1 || anyFree())
      }
    } else {
      // Nothing is known about the page: the card docks at a fixed place, a bottom corner above the Dock (the nearer one first, then the top ones).
      const nearFirst = (a: number, b: number): number => Math.abs(a - tc.x) - Math.abs(b - tc.x)
      const xs = [safe.x + size.w / 2, right(safe) - size.w / 2].sort(nearFirst).map((cx) => cx - size.w / 2)
      for (const y of [bottom(safe) - size.h, safe.y]) for (const x of xs) if (ok(make(x, y))) return done(make(x, y), 'corner', null)
    }
    // Nothing fits beside the target: the free corner of the work area farthest from it.
    const corners = [make(safe.x, safe.y), make(right(safe) - size.w, safe.y), make(safe.x, bottom(safe) - size.h), make(right(safe) - size.w, bottom(safe) - size.h)]
    const ranked = corners
      .map((r) => ({ r, overlap: overlapArea(r, target) + avoid.reduce((s, a) => s + overlapArea(r, a), 0), d: dist(centre(r), tc) }))
      .sort((a, b) => a.overlap - b.overlap || b.d - a.d)
    return done(ranked[0].r, 'corner', known ? anyFree() : null)
  }

  const pt = o.anchorPoint
  if (pt) {
    if (known) {
      // Near the point, in the nearest spot that covers no content.
      const all = gridCands().filter((c) => ok(c.rect))
      if (all.length > 0) {
        const best = all.sort((a, b) => Math.round(coverOf(a.rect)) - Math.round(coverOf(b.rect)) || dist(centre(a.rect), pt) - dist(centre(b.rect), pt))[0]
        return done(best.rect, 'near', coverOf(best.rect) < 1 || anyFree())
      }
    }
    // Near the point, below and to the right of it, so the worker's eyes (and the cursor) are not covered.
    const near = make(clamp(pt.x + 18, safe.x, right(safe) - size.w), clamp(pt.y + 22, safe.y, bottom(safe) - size.h))
    if (overlapArea(near, { x: pt.x - 6, y: pt.y - 6, w: 12, h: 12 }) === 0 && clearOf(near)) return done(near, 'near', null)
    return done(make(clamp(pt.x + 18, safe.x, right(safe) - size.w), clamp(pt.y - 22 - size.h, safe.y, bottom(safe) - size.h)), 'near', null)
  }
  // Nothing to be near: bottom right of the work area, above the Dock. When another window of ours is there (the Knack corner column), stack above it, else take another corner.
  const home = make(right(safe) - size.w, bottom(safe) - size.h)
  if (ok(home)) return done(home, 'corner', null)
  const blocking = avoid.filter((a) => overlapArea(home, a) > 0)
  const above = make(home.x, Math.min(...blocking.map((a) => a.y)) - gap - size.h)
  if (blocking.length > 0 && ok(above)) return done(above, 'corner', null)
  const others = [make(safe.x, bottom(safe) - size.h), make(right(safe) - size.w, safe.y), make(safe.x, safe.y)]
  return done(others.find(ok) ?? home, 'corner', null)
}

// The panel window is its content plus room for the shadow. The content, not the window, is what keeps its distance from the target.
export const PANEL_PAD = 6

/** Places the window of a panel whose window size (content plus padding) is `size`; the returned rect is the window, the content sits PANEL_PAD inside. */
export function placeWindow(size: { w: number; h: number }, target: Rect | null, work: Rect, o: PlaceOptions = {}): Placed {
  const inner = { w: Math.max(0, size.w - 2 * PANEL_PAD), h: Math.max(0, size.h - 2 * PANEL_PAD) }
  const placed = placePanel(inner, target, work, o)
  return { ...placed, rect: { x: placed.rect.x - PANEL_PAD, y: placed.rect.y - PANEL_PAD, w: size.w, h: size.h } }
}
