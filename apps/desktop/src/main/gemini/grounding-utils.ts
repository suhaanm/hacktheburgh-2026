// Coordinate conversion and sanity checks for grounding. This is the ONLY place Gemini's
// [ymin, xmin, ymax, xmax] box order and computer_use's 0-999 ints are converted to our
// normalised 0-1000 NormBox / NormPoint (origin top-left, x right, y down).
import type { NormBox, NormPoint } from '../../shared/protocol'

export const MAX_BOX_AREA_FRACTION = 0.5 // a box over half the screen is "didn't really find it"
export const MIN_BOX_SIDE = 3 // normalised units; ~4px on a 1440-wide screen

export const clampNorm = (n: number): number => Math.min(1000, Math.max(0, n))

export function clampBox(b: NormBox): NormBox {
  return { xmin: clampNorm(b.xmin), ymin: clampNorm(b.ymin), xmax: clampNorm(b.xmax), ymax: clampNorm(b.ymax) }
}

/** Gemini box_2d is [ymin, xmin, ymax, xmax] in 0-1000. Returns null for malformed input. */
export function fromGeminiBox(box: readonly number[] | null | undefined): NormBox | null {
  if (!box || box.length !== 4 || box.some((n) => typeof n !== 'number' || !Number.isFinite(n))) return null
  const [ymin, xmin, ymax, xmax] = box
  if (xmin === 0 && ymin === 0 && xmax === 0 && ymax === 0) return null // the schema's "not found" placeholder
  // Tolerate a swapped corner order, but never invent a box from nothing.
  const b = clampBox({ xmin: Math.min(xmin, xmax), ymin: Math.min(ymin, ymax), xmax: Math.max(xmin, xmax), ymax: Math.max(ymin, ymax) })
  return b
}

/** computer_use coordinates are ints 0-999 on both axes. */
export function fromComputerUsePoint(x: number, y: number): NormPoint | null {
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null
  return { x: clampNorm(Math.round(x)), y: clampNorm(Math.round(y)) }
}

export const boxWidth = (b: NormBox) => b.xmax - b.xmin
export const boxHeight = (b: NormBox) => b.ymax - b.ymin
export const boxArea = (b: NormBox) => (boxWidth(b) * boxHeight(b)) / 1_000_000 // fraction of the screen
export const boxCenter = (b: NormBox): NormPoint => ({ x: (b.xmin + b.xmax) / 2, y: (b.ymin + b.ymax) / 2 })

export type BoxProblem = 'degenerate' | 'oversize'
/** Null when the box is plausible for a UI element; otherwise why it is rejected. */
export function boxProblem(b: NormBox): BoxProblem | null {
  if (boxWidth(b) < MIN_BOX_SIDE || boxHeight(b) < MIN_BOX_SIDE) return 'degenerate'
  if (boxArea(b) > MAX_BOX_AREA_FRACTION) return 'oversize'
  return null
}

/** A small box around a point, for fallbacks that only know where to click. */
export function boxAroundPoint(p: NormPoint, halfSide = 25): NormBox {
  return clampBox({ xmin: p.x - halfSide, ymin: p.y - halfSide, xmax: p.x + halfSide, ymax: p.y + halfSide })
}

export const pointInBox = (p: NormPoint, b: NormBox) => p.x >= b.xmin && p.x <= b.xmax && p.y >= b.ymin && p.y <= b.ymax

export function iou(a: NormBox, b: NormBox): number {
  const ix = Math.max(0, Math.min(a.xmax, b.xmax) - Math.max(a.xmin, b.xmin))
  const iy = Math.max(0, Math.min(a.ymax, b.ymax) - Math.max(a.ymin, b.ymin))
  const inter = ix * iy
  const union = boxWidth(a) * boxHeight(a) + boxWidth(b) * boxHeight(b) - inter
  return union > 0 ? inter / union : 0
}
