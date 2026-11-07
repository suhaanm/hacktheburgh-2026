// Label placement so ring labels, bubbles and notes stay on screen and off the marks they describe.
// Pure and deterministic: the scene passes measured (or estimated) sizes in; rects come out.
import { clampRectInto, containsRect, overlapArea, type Pt, type Rect, type Size } from './geometry'

export type Side = 'below' | 'above' | 'right' | 'left'

export interface LabelRequest {
  id: string
  size: Size
  // The thing being labelled. The label sits outside it.
  anchor: Rect
  // Gap between anchor and label (include the tail length for bubbles).
  gap: number
  prefer?: Side[]
}

export interface PlacedLabel {
  id: string
  rect: Rect
  side: Side
  // Point on the label's near edge facing the anchor centre; bubble tails point from here to the anchor.
  attach: Pt
  // True when no candidate was free and the least-bad one was used.
  crowded: boolean
}

const DEFAULT_ORDER: Side[] = ['below', 'above', 'right', 'left']

function candidate(req: LabelRequest, side: Side): Rect {
  const { anchor, size, gap } = req
  const cx = anchor.x + anchor.w / 2
  const cy = anchor.y + anchor.h / 2
  switch (side) {
    case 'below':
      return { x: cx - size.width / 2, y: anchor.y + anchor.h + gap, w: size.width, h: size.height }
    case 'above':
      return { x: cx - size.width / 2, y: anchor.y - gap - size.height, w: size.width, h: size.height }
    case 'right':
      return { x: anchor.x + anchor.w + gap, y: cy - size.height / 2, w: size.width, h: size.height }
    case 'left':
      return { x: anchor.x - gap - size.width, y: cy - size.height / 2, w: size.width, h: size.height }
  }
}

export function placeLabel(req: LabelRequest, vp: Size, obstacles: Rect[], margin = 14): PlacedLabel {
  const viewport: Rect = { x: margin, y: margin, w: vp.width - margin * 2, h: vp.height - margin * 2 }
  const order = [...(req.prefer ?? []), ...DEFAULT_ORDER.filter((s) => !(req.prefer ?? []).includes(s))]
  let best: { side: Side; rect: Rect; cost: number } | null = null
  for (const side of order) {
    const raw = candidate(req, side)
    // Sliding along the anchor edge is fine; spilling off-screen is not. Clamp, then measure the damage.
    const rect = clampRectInto(raw, vp, margin)
    const offscreen = containsRect(viewport, raw) ? 0 : 1
    const shifted = Math.abs(rect.x - raw.x) + Math.abs(rect.y - raw.y)
    const hits = obstacles.reduce((sum, o) => sum + overlapArea(rect, o), 0)
    const cost = hits * 4 + shifted * 20 + offscreen * 50 + order.indexOf(side) * 2
    if (!best || cost < best.cost) best = { side, rect, cost }
    if (hits === 0 && shifted === 0) {
      best = { side, rect, cost }
      break
    }
  }
  const chosen = best ?? { side: 'below' as Side, rect: candidate(req, 'below'), cost: Infinity }
  return { id: req.id, rect: chosen.rect, side: chosen.side, attach: attachPoint(chosen.rect, chosen.side, req.anchor), crowded: chosen.cost >= 50 }
}

function attachPoint(rect: Rect, side: Side, anchor: Rect): Pt {
  const ax = anchor.x + anchor.w / 2
  const ay = anchor.y + anchor.h / 2
  switch (side) {
    case 'below':
      return { x: Math.min(rect.x + rect.w, Math.max(rect.x, ax)), y: rect.y }
    case 'above':
      return { x: Math.min(rect.x + rect.w, Math.max(rect.x, ax)), y: rect.y + rect.h }
    case 'right':
      return { x: rect.x, y: Math.min(rect.y + rect.h, Math.max(rect.y, ay)) }
    case 'left':
      return { x: rect.x + rect.w, y: Math.min(rect.y + rect.h, Math.max(rect.y, ay)) }
  }
}

// Greedy, in request order: earlier requests get first pick, later ones avoid them.
export function placeLabels(reqs: LabelRequest[], vp: Size, obstacles: Rect[], margin = 14): Map<string, PlacedLabel> {
  const placed = new Map<string, PlacedLabel>()
  const taken = [...obstacles]
  for (const req of reqs) {
    const p = placeLabel(req, vp, taken, margin)
    placed.set(req.id, p)
    taken.push(p.rect)
  }
  return placed
}

// Cheap size guess used until the DOM has measured the real label (average glyph ~0.55em).
export function estimateTextBox(text: string, fontSize: number, lineHeight: number, padX: number, padY: number, maxWidth: number): Size {
  const glyph = fontSize * 0.55
  const maxText = Math.max(glyph, maxWidth - padX * 2)
  const perLine = Math.max(1, Math.floor(maxText / glyph))
  const words = text.split(/\s+/).filter(Boolean)
  let lines = 1
  let cur = 0
  for (const w of words) {
    const len = w.length
    if (cur === 0) cur = len
    else if (cur + 1 + len <= perLine) cur += 1 + len
    else {
      lines += 1
      cur = len
    }
  }
  const widest = Math.min(maxText, Math.max(...(words.length ? words.map((w) => w.length) : [1]), Math.min(text.length, perLine)) * glyph)
  return { width: Math.ceil(Math.min(maxWidth, widest + padX * 2)), height: Math.ceil(lines * fontSize * lineHeight + padY * 2) }
}
