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

// Inverse of normToPoints (global screen points -> NormPoint 0-1000, unrounded so an exact AX centre survives the round trip).
export function pointsToNorm(p: { x: number; y: number }, bounds: DisplayBounds): NormPoint {
  const c = (n: number): number => Math.min(1000, Math.max(0, n))
  return { x: c(((p.x - bounds.x) / bounds.width) * 1000), y: c(((p.y - bounds.y) / bounds.height) * 1000) }
}
