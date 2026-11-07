// Adapted from farzaa/clicky (MIT) — leanring-buddy/OverlayWindow.swift (animateBezierFlightArc), windows/src/Clicky.Overlay/OverlayWindowManager.cs (FlyToSequence)
// Quadratic bezier arc, smoothstep ease, scale pulse sin(pi*t), heading from the curve tangent; several points are visited
// in order. Constants come from DESIGN's ghostCursor.flight tokens. Pure: no DOM, no clocks. Visual only: never clicks.
import { distance, type Pt } from './geometry'

export interface FlightStyle {
  minMs: number
  maxMs: number
  pxPerSec: number
  arcHeightFraction: number
  easing: string
  dwellMs: number
}

export interface FlightSegment {
  from: Pt
  to: Pt
  control: Pt
  durationMs: number
  // Pause after landing on `to` before the next segment starts.
  holdMs: number
}

export interface FlightPlan {
  segments: FlightSegment[]
  totalMs: number
  end: Pt
}

export interface FlightSample {
  pos: Pt
  // Direction of travel in degrees (0 = right, 90 = down). Holds the last heading while dwelling.
  headingDeg: number
  // 1 at rest, up to ~1.3 mid-flight (Clicky's swoop).
  scale: number
  phase: 'flying' | 'holding' | 'done'
  segment: number
  // 0..1 progress of the "click echo" at the final point; null when not pressing.
  press: number | null
}

const MAX_ARC_PX = 140

export function parseEasing(css: string): (t: number) => number {
  const m = /cubic-bezier\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)/.exec(css)
  if (!m) return smoothstep
  const [x1, y1, x2, y2] = [Number(m[1]), Number(m[2]), Number(m[3]), Number(m[4])]
  const ax = 3 * x1 - 3 * x2 + 1
  const bx = 3 * x2 - 6 * x1
  const cx = 3 * x1
  const ay = 3 * y1 - 3 * y2 + 1
  const by = 3 * y2 - 6 * y1
  const cy = 3 * y1
  const sx = (t: number): number => ((ax * t + bx) * t + cx) * t
  const sy = (t: number): number => ((ay * t + by) * t + cy) * t
  const dx = (t: number): number => (3 * ax * t + 2 * bx) * t + cx
  return (x: number): number => {
    if (x <= 0) return 0
    if (x >= 1) return 1
    let t = x
    for (let i = 0; i < 8; i++) {
      const err = sx(t) - x
      if (Math.abs(err) < 1e-5) break
      const d = dx(t)
      if (Math.abs(d) < 1e-6) break
      t -= err / d
    }
    if (sx(t) - x > 1e-3 || x - sx(t) > 1e-3) {
      let lo = 0
      let hi = 1
      t = x
      for (let i = 0; i < 24; i++) {
        const v = sx(t)
        if (Math.abs(v - x) < 1e-5) break
        if (v < x) lo = t
        else hi = t
        t = (lo + hi) / 2
      }
    }
    return sy(t)
  }
}

export function smoothstep(t: number): number {
  const c = Math.min(1, Math.max(0, t))
  return c * c * (3 - 2 * c)
}

export function planSegment(from: Pt, to: Pt, style: FlightStyle, holdMs: number): FlightSegment {
  const dist = distance(from, to)
  const durationMs = Math.min(style.maxMs, Math.max(style.minMs, (dist / style.pxPerSec) * 1000))
  const mid = { x: (from.x + to.x) / 2, y: (from.y + to.y) / 2 }
  const arc = Math.min(dist * style.arcHeightFraction, MAX_ARC_PX)
  // Lift the control point upward (negative y) so the cursor flies a gentle parabola; Clicky does the same.
  return { from, to, control: { x: mid.x, y: mid.y - arc }, durationMs, holdMs }
}

// `points` are already in px. A single point flies in from `startHint` (or an offset fallback).
// Intermediate waypoints hold 70% of dwellMs; the last holds the full dwell (and shows the press echo).
export function planFlight(points: Pt[], style: FlightStyle, opts: { startHint?: Pt; viewport?: { width: number; height: number } } = {}): FlightPlan {
  if (points.length === 0) return { segments: [], totalMs: 0, end: { x: 0, y: 0 } }
  const pts = [...points]
  if (pts.length === 1) {
    const end = pts[0]
    const vp = opts.viewport
    const fallback = { x: end.x - 260, y: end.y + 190 }
    const start = opts.startHint ?? (vp ? { x: Math.min(Math.max(fallback.x, 24), vp.width - 24), y: Math.min(Math.max(fallback.y, 24), vp.height - 24) } : fallback)
    pts.unshift(start)
  }
  const segments: FlightSegment[] = []
  for (let i = 1; i < pts.length; i++) {
    const last = i === pts.length - 1
    segments.push(planSegment(pts[i - 1], pts[i], style, last ? style.dwellMs : Math.round(style.dwellMs * 0.7)))
  }
  const totalMs = segments.reduce((sum, s) => sum + s.durationMs + s.holdMs, 0)
  return { segments, totalMs, end: pts[pts.length - 1] }
}

export function bezierAt(seg: FlightSegment, t: number): Pt {
  const u = 1 - t
  return {
    x: u * u * seg.from.x + 2 * u * t * seg.control.x + t * t * seg.to.x,
    y: u * u * seg.from.y + 2 * u * t * seg.control.y + t * t * seg.to.y,
  }
}

export function tangentAt(seg: FlightSegment, t: number): Pt {
  const u = 1 - t
  return {
    x: 2 * u * (seg.control.x - seg.from.x) + 2 * t * (seg.to.x - seg.control.x),
    y: 2 * u * (seg.control.y - seg.from.y) + 2 * t * (seg.to.y - seg.control.y),
  }
}

const headingOf = (v: Pt): number => (Math.atan2(v.y, v.x) * 180) / Math.PI

export function sampleFlight(plan: FlightPlan, elapsedMs: number, ease: (t: number) => number, pressMs = 0): FlightSample {
  if (plan.segments.length === 0) return { pos: plan.end, headingDeg: 0, scale: 1, phase: 'done', segment: 0, press: null }
  let t = Math.max(0, elapsedMs)
  for (let i = 0; i < plan.segments.length; i++) {
    const seg = plan.segments[i]
    if (t < seg.durationMs) {
      const lin = t / seg.durationMs
      const e = ease(lin)
      return {
        pos: bezierAt(seg, e),
        headingDeg: headingOf(tangentAt(seg, e)),
        scale: 1 + Math.sin(lin * Math.PI) * 0.3,
        phase: 'flying',
        segment: i,
        press: null,
      }
    }
    t -= seg.durationMs
    const last = i === plan.segments.length - 1
    if (t < seg.holdMs) {
      const press = last && pressMs > 0 && t >= 120 ? Math.min(1, (t - 120) / pressMs) : null
      return { pos: seg.to, headingDeg: headingOf(tangentAt(seg, 1)), scale: 1, phase: 'holding', segment: i, press }
    }
    t -= seg.holdMs
  }
  const lastSeg = plan.segments[plan.segments.length - 1]
  return { pos: plan.end, headingDeg: headingOf(tangentAt(lastSeg, 1)), scale: 1, phase: 'done', segment: plan.segments.length - 1, press: null }
}

// Cursor-pointer lean: a pointer arrow should not spin like Clicky's triangle, so map the heading to +-lean degrees.
export function leanDeg(headingDeg: number, maxLean = 16): number {
  // Heading 0 (right) and 180 (left) lean slightly; vertical travel leans the other way. Smooth, bounded.
  const rad = (headingDeg * Math.PI) / 180
  return Math.max(-maxLean, Math.min(maxLean, -Math.cos(rad) * maxLean * 0.6 + Math.sin(rad) * maxLean * 0.4))
}
