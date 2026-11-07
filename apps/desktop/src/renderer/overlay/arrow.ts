// Adapted from farzaa/clicky (MIT) — windows/src/Clicky.Overlay/DrawingOverlayControl.cs (BuildArrowHead: head length and spread)
// Planned so the arrow never covers its target, stays on screen and avoids other marks. Arrows are guidance only; they
// never become click targets (the overlay is click-through).
import type { NormBox, NormPoint } from '../../shared/protocol'
import { clampPoint, distance, inflate, normToPx, rectCenter, targetRect, type Pt, type Rect, type Size } from './geometry'

export interface ArrowStyleTokens {
  headLength: number
  headWidth: number
  gap: number
  curvature: number
  minLength: number
}

export interface ArrowPlan {
  start: Pt
  // Tip of the head, `gap` px short of the target.
  tip: Pt
  control: Pt
  // Where the shaft stops (under the head).
  shaftEnd: Pt
  head: [Pt, Pt, Pt]
  target: Rect
}

// Approach directions (unit vectors in the direction of travel), most natural first: from upper-left, left, above...
const APPROACH: Pt[] = [
  { x: Math.SQRT1_2, y: Math.SQRT1_2 },
  { x: 1, y: 0 },
  { x: 0, y: 1 },
  { x: -Math.SQRT1_2, y: Math.SQRT1_2 },
  { x: Math.SQRT1_2, y: -Math.SQRT1_2 },
  { x: -1, y: 0 },
  { x: 0, y: -1 },
  { x: -Math.SQRT1_2, y: -Math.SQRT1_2 },
]

function boundaryDistance(half: { w: number; h: number }, dir: Pt): number {
  const tx = Math.abs(dir.x) < 1e-9 ? Infinity : half.w / Math.abs(dir.x)
  const ty = Math.abs(dir.y) < 1e-9 ? Infinity : half.h / Math.abs(dir.y)
  return Math.min(tx, ty)
}

function segmentHitsRect(a: Pt, b: Pt, r: Rect): boolean {
  for (let i = 0; i <= 12; i++) {
    const t = i / 12
    const x = a.x + (b.x - a.x) * t
    const y = a.y + (b.y - a.y) * t
    if (x >= r.x && x <= r.x + r.w && y >= r.y && y <= r.y + r.h) return true
  }
  return false
}

export interface PlanArrowInput {
  to: NormPoint | NormBox
  from?: NormPoint
  vp: Size
  style: ArrowStyleTokens
  // Half-size of the square drawn around a point target (so the arrow stops short of a believable "button").
  pointHalf: number
  // Other marks the shaft should not cross (rings, labels, ...).
  avoid?: Rect[]
  // Aim at this rect instead of `to` (the union of the target and any ring/badge drawn around it).
  targetRect?: Rect
}

export function planArrow(input: PlanArrowInput): ArrowPlan {
  const { to, from, vp, style, pointHalf, avoid = [] } = input
  const target = input.targetRect ?? targetRect(to, vp, pointHalf)
  const keepOut = inflate(target, style.gap)
  const center = rectCenter(target)
  const half = { w: keepOut.w / 2, h: keepOut.h / 2 }
  const margin = Math.max(style.headWidth, 16)

  let start: Pt
  let tip: Pt
  if (from) {
    start = clampPoint(normToPx(from, vp), vp, margin)
    const dir = unit({ x: center.x - start.x, y: center.y - start.y })
    tip = dir ? { x: center.x - dir.x * boundaryDistance(half, dir), y: center.y - dir.y * boundaryDistance(half, dir) } : { x: center.x, y: keepOut.y }
    // `from` inside (or hugging) the keep-out box: fall back to the automatic choice.
    const inside = start.x >= keepOut.x && start.x <= keepOut.x + keepOut.w && start.y >= keepOut.y && start.y <= keepOut.y + keepOut.h
    if (inside || distance(start, tip) < style.minLength * 0.6) return planArrow({ ...input, from: undefined })
    // A start right next to the target would leave a stub that reads as a cursor: extend it back along the line.
    const span = distance(start, tip)
    if (dir && span < style.minLength) start = clampPoint({ x: tip.x - dir.x * style.minLength, y: tip.y - dir.y * style.minLength }, vp, margin)
  } else {
    const wanted = Math.max(style.minLength, style.headLength * 4.2)
    let best: { score: number; start: Pt; tip: Pt } | null = null
    APPROACH.forEach((dir, index) => {
      const t = boundaryDistance(half, dir)
      const candidateTip = { x: center.x - dir.x * t, y: center.y - dir.y * t }
      // Longest length that keeps the start inside the viewport.
      let len = wanted
      while (len > 0) {
        const s = { x: candidateTip.x - dir.x * len, y: candidateTip.y - dir.y * len }
        if (s.x >= margin && s.x <= vp.width - margin && s.y >= margin && s.y <= vp.height - margin) break
        len -= 8
      }
      const s = { x: candidateTip.x - dir.x * len, y: candidateTip.y - dir.y * len }
      let score = len - index * 3
      if (len < style.minLength) score -= 1000
      if (avoid.some((r) => segmentHitsRect(s, candidateTip, r))) score -= 200
      if (!best || score > best.score) best = { score, start: s, tip: candidateTip }
    })
    const chosen = best ?? { score: 0, start: { x: center.x - wanted, y: center.y }, tip: { x: keepOut.x, y: center.y } }
    start = chosen.start
    tip = chosen.tip
  }

  const length = distance(start, tip)
  const mid = { x: (start.x + tip.x) / 2, y: (start.y + tip.y) / 2 }
  const dir = unit({ x: tip.x - start.x, y: tip.y - start.y }) ?? { x: 1, y: 0 }
  // Bow the shaft upward (negative y) a little: reads as a hand-drawn arrow, and keeps the head tangent honest.
  let perp = { x: -dir.y, y: dir.x }
  if (perp.y > 0) perp = { x: -perp.x, y: -perp.y }
  const control = { x: mid.x + perp.x * style.curvature * length, y: mid.y + perp.y * style.curvature * length }
  const tdir = unit({ x: tip.x - control.x, y: tip.y - control.y }) ?? dir
  const baseCenter = { x: tip.x - tdir.x * style.headLength, y: tip.y - tdir.y * style.headLength }
  const hw = style.headWidth / 2
  const normal = { x: -tdir.y, y: tdir.x }
  const head: [Pt, Pt, Pt] = [tip, { x: baseCenter.x + normal.x * hw, y: baseCenter.y + normal.y * hw }, { x: baseCenter.x - normal.x * hw, y: baseCenter.y - normal.y * hw }]
  const shaftEnd = { x: tip.x - tdir.x * style.headLength * 0.8, y: tip.y - tdir.y * style.headLength * 0.8 }
  return { start, tip, control, shaftEnd, head, target }
}

function unit(v: Pt): Pt | null {
  const len = Math.hypot(v.x, v.y)
  return len < 1e-6 ? null : { x: v.x / len, y: v.y / len }
}

export function arrowShaftPath(plan: ArrowPlan): string {
  return `M ${plan.start.x.toFixed(1)} ${plan.start.y.toFixed(1)} Q ${plan.control.x.toFixed(1)} ${plan.control.y.toFixed(1)} ${plan.shaftEnd.x.toFixed(1)} ${plan.shaftEnd.y.toFixed(1)}`
}

export function arrowHeadPoints(plan: ArrowPlan): string {
  return plan.head.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
}
