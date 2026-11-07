// Adapted from farzaa/clicky (MIT) — leanring-buddy/CompanionManager.swift (screenshot pixel -> screen point mapping, L648-682), CompanionScreenCaptureUtility.swift
// Coordinate mapping for everything drawn on (or captured from) a display.
// Annotations are normalised 0-1000 from the top-left of the target display (x right, y down).
// The overlay window fills one display, so CSS px = norm / 1000 * window size. Global screen points are in
// DIPs (Electron/macOS points); physical pixels = DIPs * scaleFactor. Clicky's double Y-flip (screenshot ->
// AppKit bottom-left -> SwiftUI top-left) is deliberately gone: everything stays top-left.
import type { NormBox, NormPoint } from '../../shared/protocol'

export interface Pt {
  x: number
  y: number
}
export interface Size {
  width: number
  height: number
}
export interface Rect {
  x: number
  y: number
  w: number
  h: number
}
export interface DisplayGeometry {
  // Electron display.bounds: global DIPs; the primary display is at (0,0), others may be negative.
  bounds: { x: number; y: number; width: number; height: number }
  scaleFactor: number
}

export const NORM_MAX = 1000

const clamp = (n: number, lo: number, hi: number): number => Math.min(hi, Math.max(lo, n))

export function isNormBox(v: NormPoint | NormBox): v is NormBox {
  return 'xmin' in v
}

export function normToPx(p: NormPoint, vp: Size): Pt {
  return { x: (p.x / NORM_MAX) * vp.width, y: (p.y / NORM_MAX) * vp.height }
}

export function pxToNorm(p: Pt, vp: Size, opts: { clamp?: boolean } = {}): NormPoint {
  const n = { x: (p.x / vp.width) * NORM_MAX, y: (p.y / vp.height) * NORM_MAX }
  return opts.clamp ? { x: clamp(n.x, 0, NORM_MAX), y: clamp(n.y, 0, NORM_MAX) } : n
}

// Tolerates swapped min/max (models sometimes return them) and clamps into the display.
export function normBoxToRect(b: NormBox, vp: Size): Rect {
  const x0 = clamp(Math.min(b.xmin, b.xmax), 0, NORM_MAX)
  const x1 = clamp(Math.max(b.xmin, b.xmax), 0, NORM_MAX)
  const y0 = clamp(Math.min(b.ymin, b.ymax), 0, NORM_MAX)
  const y1 = clamp(Math.max(b.ymin, b.ymax), 0, NORM_MAX)
  return {
    x: (x0 / NORM_MAX) * vp.width,
    y: (y0 / NORM_MAX) * vp.height,
    w: ((x1 - x0) / NORM_MAX) * vp.width,
    h: ((y1 - y0) / NORM_MAX) * vp.height,
  }
}

export function rectToNormBox(r: Rect, vp: Size): NormBox {
  return {
    xmin: (r.x / vp.width) * NORM_MAX,
    ymin: (r.y / vp.height) * NORM_MAX,
    xmax: ((r.x + r.w) / vp.width) * NORM_MAX,
    ymax: ((r.y + r.h) / vp.height) * NORM_MAX,
  }
}

// ---- global screen <-> norm (window not at origin, retina) ----

export function screenDipToNorm(p: Pt, display: DisplayGeometry, opts: { clamp?: boolean } = {}): NormPoint {
  const { bounds } = display
  return pxToNorm({ x: p.x - bounds.x, y: p.y - bounds.y }, { width: bounds.width, height: bounds.height }, opts)
}

export function normToScreenDip(p: NormPoint, display: DisplayGeometry): Pt {
  const { bounds } = display
  const local = normToPx(p, { width: bounds.width, height: bounds.height })
  return { x: bounds.x + local.x, y: bounds.y + local.y }
}

// Physical pixel on this display's own framebuffer (origin = display top-left), e.g. a full-res desktopCapturer frame.
export function normToDisplayPhysicalPx(p: NormPoint, display: DisplayGeometry): Pt {
  const local = normToPx(p, { width: display.bounds.width * display.scaleFactor, height: display.bounds.height * display.scaleFactor })
  return { x: Math.round(local.x), y: Math.round(local.y) }
}

export function displayPhysicalPxToNorm(p: Pt, display: DisplayGeometry): NormPoint {
  return pxToNorm(p, { width: display.bounds.width * display.scaleFactor, height: display.bounds.height * display.scaleFactor })
}

// Screenshot pixels (any downscale of the display) <-> norm. Independent of scaleFactor by construction.
export function shotPxToNorm(p: Pt, shot: { widthPx: number; heightPx: number }): NormPoint {
  return pxToNorm(p, { width: shot.widthPx, height: shot.heightPx })
}
export function normToShotPx(p: NormPoint, shot: { widthPx: number; heightPx: number }): Pt {
  return normToPx(p, { width: shot.widthPx, height: shot.heightPx })
}

// ---- rect helpers ----

export const rectCenter = (r: Rect): Pt => ({ x: r.x + r.w / 2, y: r.y + r.h / 2 })
export const rectRight = (r: Rect): number => r.x + r.w
export const rectBottom = (r: Rect): number => r.y + r.h

export function inflate(r: Rect, pad: number): Rect {
  return { x: r.x - pad, y: r.y - pad, w: r.w + pad * 2, h: r.h + pad * 2 }
}

// Grow (never shrink) to a minimum size, keeping the centre.
export function atLeast(r: Rect, minW: number, minH = minW): Rect {
  const w = Math.max(r.w, minW)
  const h = Math.max(r.h, minH)
  return { x: r.x - (w - r.w) / 2, y: r.y - (h - r.h) / 2, w, h }
}

export function pointRect(p: Pt, half: number): Rect {
  return { x: p.x - half, y: p.y - half, w: half * 2, h: half * 2 }
}

export function unionRect(rects: Rect[]): Rect {
  const x0 = Math.min(...rects.map((r) => r.x))
  const y0 = Math.min(...rects.map((r) => r.y))
  const x1 = Math.max(...rects.map((r) => r.x + r.w))
  const y1 = Math.max(...rects.map((r) => r.y + r.h))
  return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 }
}

export function overlapArea(a: Rect, b: Rect): number {
  const w = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x)
  const h = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y)
  return w > 0 && h > 0 ? w * h : 0
}

export function containsRect(outer: Rect, inner: Rect): boolean {
  return inner.x >= outer.x && inner.y >= outer.y && inner.x + inner.w <= outer.x + outer.w && inner.y + inner.h <= outer.y + outer.h
}

// Shift a rect (never resize) so it sits inside the viewport with a margin.
export function clampRectInto(r: Rect, vp: Size, margin = 0): Rect {
  const maxX = Math.max(margin, vp.width - margin - r.w)
  const maxY = Math.max(margin, vp.height - margin - r.h)
  return { x: clamp(r.x, margin, maxX), y: clamp(r.y, margin, maxY), w: r.w, h: r.h }
}

export function clampPoint(p: Pt, vp: Size, margin = 0): Pt {
  return { x: clamp(p.x, margin, vp.width - margin), y: clamp(p.y, margin, vp.height - margin) }
}

export const distance = (a: Pt, b: Pt): number => Math.hypot(b.x - a.x, b.y - a.y)

// Rect for an arrow/label target: a box maps to itself; a point becomes a square of `pointHalf` around it.
export function targetRect(to: NormPoint | NormBox, vp: Size, pointHalf: number): Rect {
  if (isNormBox(to)) return normBoxToRect(to, vp)
  return pointRect(normToPx(to, vp), pointHalf)
}
