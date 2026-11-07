// NormPoint (0-1000, top-left of the display) -> global screen points (what osascript System Events clicks in).
// Points, not device pixels: on a retina display the scale factor is already folded into `bounds` (DIPs).
import type { NormPoint } from '../../shared/protocol'

export interface DisplayBounds {
  x: number
  y: number
  width: number
  height: number
}

export function normToPoints(p: NormPoint, bounds: DisplayBounds): { x: number; y: number } {
  return { x: Math.round(bounds.x + (p.x / 1000) * bounds.width), y: Math.round(bounds.y + (p.y / 1000) * bounds.height) }
}

export function isValidNormPoint(p: NormPoint): boolean {
  return Number.isFinite(p.x) && Number.isFinite(p.y) && p.x >= 0 && p.x <= 1000 && p.y >= 0 && p.y <= 1000
}

// A screenshot only maps onto the display if it has the display's shape (the same aspect ratio, within 2%). A capture of another display, a
// crop or a stale frame has a different shape, and a click computed from it would land somewhere else.
export function aspectMatches(shot: { widthPx: number; heightPx: number }, display: { width: number; height: number }, tolerance = 0.02): boolean {
  if (!(shot.widthPx > 0 && shot.heightPx > 0 && display.width > 0 && display.height > 0)) return false
  const a = shot.widthPx / shot.heightPx
  const b = display.width / display.height
  return Math.abs(a - b) / b <= tolerance
}

// Inverse of normToPoints (global screen points -> NormPoint 0-1000, unrounded so an exact AX centre survives the round trip).
export function pointsToNorm(p: { x: number; y: number }, bounds: DisplayBounds): NormPoint {
  const c = (n: number): number => Math.min(1000, Math.max(0, n))
  return { x: c(((p.x - bounds.x) / bounds.width) * 1000), y: c(((p.y - bounds.y) / bounds.height) * 1000) }
}
