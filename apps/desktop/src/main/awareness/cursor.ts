// Cursor features (AWR-1). Electron's screen.getCursorScreenPoint() needs no macOS permission. It is sampled at about 15 Hz and each
// two-second window is reduced to a handful of numbers ON THIS MAC; the samples (and so every coordinate) are dropped when the
// window closes. Only the derived numbers, and zone ids from the pack's zone vocabulary when a resolver exists, go anywhere.
//
//   dwell        longest stay inside a 24 px square without a click, counted only from 1.2 s
//   wander       path length over displacement (displacement floored at 24 px; 1 means "went nowhere in particular", not "straight")
//   back_forth   reversals between two places at least 140 px apart (A, B, A), or zone alternations when zones are known
//   speed_bursts fast flicks over 1800 px/s
//   idle_gap     longest stretch without movement
//
// Pure functions below; the sampler at the bottom owns the only timer and only runs between start() and stop().
import { fin, ZONE_RE, realTimers, type Clock, type CursorSample, type CursorWindowFeatures, type Timers } from './types'

export const DWELL_BOX_PX = 24
export const DWELL_MIN_S = 1.2
export const WANDER_CAP = 20
export const BURST_PX_S = 1800
export const STILL_PX = 3
export const TURN_PX = 140
export const MAX_SAMPLES = 200

export type ZoneAt = (x: number, y: number) => string | null

const round2 = (v: number): number => Math.round(v * 100) / 100
const dist = (a: CursorSample, b: CursorSample): number => Math.hypot(a.x - b.x, a.y - b.y)

/** Longest run of consecutive samples whose bounding box is at most `box` px on both axes. Returns its duration and centroid. */
function longestStay(seg: readonly CursorSample[], box: number): { s: number; cx: number; cy: number } {
  let best = { s: 0, cx: 0, cy: 0 }
  for (let i = 0; i < seg.length; i++) {
    let minX = seg[i].x
    let maxX = seg[i].x
    let minY = seg[i].y
    let maxY = seg[i].y
    let sx = seg[i].x
    let sy = seg[i].y
    let j = i
    while (j + 1 < seg.length) {
      const n = seg[j + 1]
      const nMinX = Math.min(minX, n.x)
      const nMaxX = Math.max(maxX, n.x)
      const nMinY = Math.min(minY, n.y)
      const nMaxY = Math.max(maxY, n.y)
      if (nMaxX - nMinX > box || nMaxY - nMinY > box) break
      minX = nMinX
      maxX = nMaxX
      minY = nMinY
      maxY = nMaxY
      sx += n.x
      sy += n.y
      j++
    }
    const s = (seg[j].t - seg[i].t) / 1000
    if (s > best.s) best = { s, cx: sx / (j - i + 1), cy: sy / (j - i + 1) }
    if (j === seg.length - 1) break // nothing later can be longer
  }
  return best
}

/** Splits the samples at click times so a dwell never spans a click. */
function splitAtClicks(samples: readonly CursorSample[], clicks: readonly number[]): CursorSample[][] {
  if (clicks.length === 0) return [samples.slice()]
  const cuts = [...clicks].sort((a, b) => a - b)
  const out: CursorSample[][] = []
  let cur: CursorSample[] = []
  let ci = 0
  for (const s of samples) {
    while (ci < cuts.length && cuts[ci] <= s.t) {
      if (cur.length) out.push(cur)
      cur = []
      ci++
    }
    cur.push(s)
  }
  if (cur.length) out.push(cur)
  return out
}

/** Turning points by a swing filter: a leg is confirmed once the cursor has gone out at least `turn` px and come back `turn` px. */
function legs(samples: readonly CursorSample[], turn: number): Array<{ dx: number; dy: number }> {
  if (samples.length < 2) return []
  const out: Array<{ dx: number; dy: number }> = []
  let pivot = samples[0]
  let extreme = samples[0]
  for (let i = 1; i < samples.length; i++) {
    const q = samples[i]
    if (dist(q, pivot) >= dist(extreme, pivot)) extreme = q
    else if (dist(extreme, q) >= turn && dist(extreme, pivot) >= turn) {
      out.push({ dx: extreme.x - pivot.x, dy: extreme.y - pivot.y })
      pivot = extreme
      extreme = q
    }
  }
  if (dist(extreme, pivot) >= turn) out.push({ dx: extreme.x - pivot.x, dy: extreme.y - pivot.y })
  return out
}

function reversals(ls: ReadonlyArray<{ dx: number; dy: number }>): number {
  let n = 0
  for (let i = 1; i < ls.length; i++) {
    const a = ls[i - 1]
    const b = ls[i]
    const na = Math.hypot(a.dx, a.dy)
    const nb = Math.hypot(b.dx, b.dy)
    if (na === 0 || nb === 0) continue
    if ((a.dx * b.dx + a.dy * b.dy) / (na * nb) <= -0.5) n++
  }
  return n
}

/** Most frequent A, B, A pair in the zone sequence (consecutive repeats collapsed, unknown zones skipped). */
function zoneAlternation(zones: ReadonlyArray<string | null>): { count: number; a: string | null; b: string | null } {
  const seq: string[] = []
  for (const z of zones) {
    if (z === null) continue
    if (seq.length === 0 || seq[seq.length - 1] !== z) seq.push(z)
  }
  const counts = new Map<string, number>()
  let total = 0
  for (let i = 0; i + 2 < seq.length; i++) {
    if (seq[i] === seq[i + 2] && seq[i] !== seq[i + 1]) {
      const pair = [seq[i], seq[i + 1]].sort().join('|')
      counts.set(pair, (counts.get(pair) ?? 0) + 1)
      total++
    }
  }
  if (total === 0) return { count: 0, a: null, b: null }
  let bestPair = ''
  let best = 0
  for (const [pair, c] of [...counts.entries()].sort()) {
    if (c > best) {
      best = c
      bestPair = pair
    }
  }
  const [a, b] = bestPair.split('|')
  return { count: total, a, b }
}

export interface ReduceOptions {
  windowS: number
  zoneAt?: ZoneAt | null
  // Click times in the same clock as the samples; null = no click source (clicks unknown).
  clickTimes?: readonly number[] | null
}

export function emptyFeatures(windowS: number, clicks: number | null = null): CursorWindowFeatures {
  return { window_s: windowS, dwell_s: 0, dwell_zone: null, wander: 1, back_forth: 0, zone_a: null, zone_b: null, speed_bursts: 0, idle_gap_s: 0, clicks, dwell_anchor: null }
}

const safeZone = (z: string | null | undefined): string | null => (typeof z === 'string' && ZONE_RE.test(z) ? z : null)

/** Reduces one window of samples to features. Pure: no clock, no timer, no state. Non-finite samples are ignored. */
export function reduceCursorWindow(rawSamples: readonly CursorSample[], opts: ReduceOptions): CursorWindowFeatures {
  const samples = rawSamples.filter((s) => fin(s.t) && fin(s.x) && fin(s.y)).slice(-MAX_SAMPLES)
  const clicks = opts.clickTimes ?? null
  const nClicks = clicks === null ? null : clicks.filter((t) => samples.length > 0 && t >= samples[0].t && t <= samples[samples.length - 1].t + 1000).length
  if (samples.length < 2) return emptyFeatures(opts.windowS, nClicks)
  const zoneAt = opts.zoneAt ?? null

  // dwell: longest stay in a 24 px square, never across a click
  let bestDwell = { s: 0, cx: 0, cy: 0 }
  for (const seg of splitAtClicks(samples, clicks ?? [])) {
    const stay = longestStay(seg, DWELL_BOX_PX)
    if (stay.s > bestDwell.s) bestDwell = stay
  }
  const dwelling = bestDwell.s >= DWELL_MIN_S
  const dwellZone = dwelling && zoneAt ? safeZone(zoneAt(bestDwell.cx, bestDwell.cy)) : null

  // wander: path over displacement
  let path = 0
  let bursts = 0
  let inBurst = false
  for (let i = 1; i < samples.length; i++) {
    const d = dist(samples[i], samples[i - 1])
    path += d
    const dt = Math.max(20, samples[i].t - samples[i - 1].t) / 1000
    const fast = d / dt >= BURST_PX_S
    if (fast && !inBurst) bursts++
    inBurst = fast
  }
  const disp = dist(samples[0], samples[samples.length - 1])
  const wander = path < DWELL_BOX_PX ? 1 : Math.min(WANDER_CAP, path / Math.max(disp, DWELL_BOX_PX))

  // back and forth: geometry, or zone alternation when zones are known
  const geo = reversals(legs(samples, TURN_PX))
  const alt = zoneAt ? zoneAlternation(samples.map((s) => safeZone(zoneAt(s.x, s.y)))) : { count: 0, a: null, b: null }

  // idle gap: longest stretch without moving
  const still = longestStay(samples, STILL_PX)

  return {
    window_s: opts.windowS,
    dwell_s: dwelling ? round2(Math.min(bestDwell.s, opts.windowS)) : 0,
    dwell_zone: dwellZone,
    wander: round2(wander),
    back_forth: Math.min(30, Math.max(geo, alt.count)),
    zone_a: alt.a,
    zone_b: alt.b,
    speed_bursts: Math.min(30, bursts),
    idle_gap_s: round2(Math.min(still.s, opts.windowS)),
    clicks: nClicks,
    dwell_anchor: dwelling ? { bx: Math.floor(bestDwell.cx / DWELL_BOX_PX), by: Math.floor(bestDwell.cy / DWELL_BOX_PX) } : null,
  }
}

// ------------------------------------------------------------------------------------------------ sampler
export interface ClickSource {
  /** Click times since the last call, in the sampler's clock, or null when clicks cannot be known (no Accessibility). */
  drain(): number[] | null
}

/** The default: clicks are unknown. Counting global clicks needs an event tap, which needs Accessibility; it is not requested. */
export const unknownClicks: ClickSource = { drain: () => null }

/** A scripted click source for tests and mock mode: call click(t) with a time in the sampler's clock. */
export function createFakeClickSource(): ClickSource & { click(t: number): void } {
  let pending: number[] = []
  return {
    click(t) {
      pending.push(t)
    },
    drain() {
      const out = pending
      pending = []
      return out
    },
  }
}

export interface CursorSamplerDeps {
  getPoint: () => { x: number; y: number }
  now?: Clock
  timers?: Timers
  hz?: number
  windowMs?: number
  zoneAt?: ZoneAt | null
  clicks?: ClickSource
  onWindow: (features: CursorWindowFeatures, span: { t0: number; t1: number }) => void
}

export interface CursorSampler {
  start(): void
  stop(): void
  running(): boolean
  /** Take one sample now (the timer calls this; tests call it directly). */
  sample(): void
}

export function createCursorSampler(deps: CursorSamplerDeps): CursorSampler {
  const now = deps.now ?? Date.now
  const timers = deps.timers ?? realTimers
  const hz = Math.min(30, Math.max(1, deps.hz ?? 15))
  const windowMs = Math.max(500, deps.windowMs ?? 2000)
  const clicks = deps.clicks ?? unknownClicks
  let buf: CursorSample[] = []
  let clickTimes: number[] | null = []
  let t0 = 0
  let handle: unknown = null

  const close = (t1: number): void => {
    const samples = buf
    const ct = clickTimes
    buf = []
    clickTimes = ct === null ? null : []
    const start = t0
    t0 = t1
    if (samples.length === 0) return
    try {
      deps.onWindow(reduceCursorWindow(samples, { windowS: windowMs / 1000, zoneAt: deps.zoneAt ?? null, clickTimes: ct }), { t0: start, t1 })
    } catch {
      // a consumer failure must not stop sampling
    }
  }

  const sample = (): void => {
    const t = now()
    if (buf.length === 0 && t0 === 0) t0 = t
    let p: { x: number; y: number }
    try {
      p = deps.getPoint()
    } catch {
      return
    }
    if (fin(p?.x) && fin(p?.y)) buf.push({ t, x: p.x, y: p.y })
    const drained = clicks.drain()
    if (drained === null) clickTimes = null
    else if (clickTimes !== null) clickTimes.push(...drained)
    if (t - t0 >= windowMs) close(t)
  }

  return {
    start() {
      if (handle !== null) return
      buf = []
      clickTimes = []
      t0 = 0
      handle = timers.setInterval(sample, Math.round(1000 / hz))
    },
    stop() {
      if (handle !== null) timers.clearInterval(handle)
      handle = null
      buf = [] // no coordinate outlives the sampler
      clickTimes = []
      t0 = 0
    },
    running: () => handle !== null,
    sample,
  }
}
