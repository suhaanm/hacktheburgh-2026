// Loop signatures (AWR-1, SEC-7's rule applied to the worker). A "stop" (the cursor dwelling in one place) or any other action is
// reduced to a canonical signature so near-identical repeats compare equal, and a loop is the same signature four times in a row, or a
// short cycle (period 2 to 4) three times in a row. Idea from clickyyy (re-implemented, no code copied; see docs/reference-notes/clickyyy.md).
//
// What goes into a signature: the kind of action, the app kind, and a target: the capture zone when one is known, else the position
// rounded into 24 px buckets (so a cursor landing a few pixels apart still matches). Text is never in a signature; a window title,
// if a caller ever has one, may enter only as a salted short hash that lives in memory for a few minutes at most.
import { createHash, randomBytes } from 'node:crypto'

export const BUCKET_PX = 24
export const SAME_REPEATS = 4
export const CYCLE_REPEATS = 3
export const CYCLE_MIN = 2
export const CYCLE_MAX = 4
export const LOOP_RING = 24
export const LOOP_TTL_MS = 5 * 60_000

export interface ActionLike {
  kind: string // 'stop', 'click', 'key' ...
  appKind?: string
  zone?: string | null
  x?: number
  y?: number
  // A salted hash made by hashLoopText; never raw text.
  textHash?: string | null
}

const bucket = (v: number): number => Math.floor(v / BUCKET_PX)

/** Canonical form. Cosmetic fields (anything not listed) cannot change it. */
export function actionSignature(a: ActionLike): string {
  const target = a.zone ? `z:${a.zone}` : Number.isFinite(a.x) && Number.isFinite(a.y) ? `b:${bucket(a.x as number)},${bucket(a.y as number)}` : 'none'
  return [a.kind.toLowerCase(), a.appKind ?? '-', target, a.textHash ?? '-'].join('|')
}

export interface LoopHit {
  kind: 'same' | 'cycle'
  period: number
}

/** The loop at the tail of `sigs`, or null. `same`: one signature SAME_REPEATS times in a row. `cycle`: a pattern of 2 to 4 CYCLE_REPEATS times. */
export function detectLoop(sigs: readonly string[]): LoopHit | null {
  const n = sigs.length
  if (n >= SAME_REPEATS) {
    const last = sigs[n - 1]
    let run = 1
    for (let i = n - 2; i >= 0 && sigs[i] === last; i--) run++
    if (run >= SAME_REPEATS) return { kind: 'same', period: 1 }
  }
  for (let p = CYCLE_MIN; p <= CYCLE_MAX; p++) {
    if (n < p * CYCLE_REPEATS) continue
    const pattern = sigs.slice(n - p)
    if (new Set(pattern).size < 2) continue // a period-2 pattern of one repeated signature is the "same" rule's job
    let ok = true
    for (let r = 1; r < CYCLE_REPEATS && ok; r++) {
      for (let i = 0; i < p; i++) {
        if (sigs[n - p * (r + 1) + i] !== pattern[i]) {
          ok = false
          break
        }
      }
    }
    if (ok) return { kind: 'cycle', period: p }
  }
  return null
}

/** A salted short hash for a title or label, so a window can enter a loop signature without its text ever being kept. */
export function createLoopHasher(salt: Buffer = randomBytes(16)): (text: string) => string {
  return (text) => createHash('sha256').update(salt).update('\0').update(text.normalize('NFKC')).digest('hex').slice(0, 8)
}

/** Short-lived ring of signatures. Entries older than the TTL are forgotten; a loop cannot span a long gap. */
export class LoopWatcher {
  private ring: Array<{ sig: string; at: number }> = []

  constructor(
    private readonly now: () => number = Date.now,
    private readonly ttlMs = LOOP_TTL_MS,
    private readonly cap = LOOP_RING,
  ) {}

  /** Record one action; returns the loop it completes, if any. After a hit the ring is cleared so one loop fires once. */
  push(sig: string): LoopHit | null {
    const t = this.now()
    this.ring = this.ring.filter((e) => t - e.at <= this.ttlMs)
    this.ring.push({ sig, at: t })
    if (this.ring.length > this.cap) this.ring.shift()
    const hit = detectLoop(this.ring.map((e) => e.sig))
    if (hit) this.ring = []
    return hit
  }

  clear(): void {
    this.ring = []
  }

  size(): number {
    return this.ring.length
  }
}

/**
 * Turns per-window dwell features into "stop" actions: a dwell that continues from the previous window at the same place is one
 * stop, not two. Returns the signature of a NEW stop, or null.
 */
export class StopTracker {
  private lastAnchor: string | null = null

  observe(args: { dwell_s: number; anchor: { bx: number; by: number } | null; zone: string | null; appKind: string }): string | null {
    if (args.dwell_s <= 0 || !args.anchor) {
      this.lastAnchor = null
      return null
    }
    const key = args.zone ? `z:${args.zone}` : `b:${args.anchor.bx},${args.anchor.by}`
    const same = this.lastAnchor === key
    this.lastAnchor = key
    if (same) return null
    return actionSignature({ kind: 'stop', appKind: args.appKind, zone: args.zone, x: args.anchor.bx * BUCKET_PX, y: args.anchor.by * BUCKET_PX })
  }

  reset(): void {
    this.lastAnchor = null
  }
}
