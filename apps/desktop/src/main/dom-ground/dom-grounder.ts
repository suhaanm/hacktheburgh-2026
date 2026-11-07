// DOM-first grounding (COA-2): ask the browser extension where an element is, instead of guessing from pixels.
//   request()  queues a want (by salted label hash, or by role and name) and waits for the extension's answer;
//   nextWant() is what GET /ext/want returns; answer() is what POST /ext/rect delivers.
//   track()    keeps re-resolving one target while a ring is shown, so the ring follows scrolling and is HIDDEN the moment the
//              answers stop arriving or get old (COA-6: no stale arrows).
// The extension is off until the worker turns it on, and sensitive elements are never returned by it; if nothing answers, the
// caller falls back to vision (desktop apps only) or simply shows nothing.
import { randomUUID } from 'node:crypto'
import { mapAnswer, ageNow, type DisplayInfo, type Mapped, type MapFailure } from './rect-map'
import { wantFor, type DomTarget, type RectAnswer, type RectWant } from './protocol'
import type { NormBox } from '../../shared/protocol'
import type { XY } from './protocol'

export type RequestOutcome = { kind: 'answer'; answer: RectAnswer; receivedAt: number } | { kind: 'timeout' }

interface Pending {
  want: RectWant
  key: string
  issuedAt: number | null
  deadline: number
  waiters: Array<(o: RequestOutcome) => void>
  timer: unknown
}

export interface DomGrounderOptions {
  now?: () => number
  setTimer?: (fn: () => void, ms: number) => unknown
  clearTimer?: (h: unknown) => void
  id?: () => string
  // A want handed to the extension but never answered is handed out again after this long.
  reissueMs?: number
  log?: (scope: string, ...args: unknown[]) => void
}

export interface DomGrounder {
  request(target: DomTarget, opts?: { timeoutMs?: number; frameId?: string }): Promise<RequestOutcome>
  nextWant(): RectWant | null
  answer(a: RectAnswer): boolean
  // How many wants are waiting (for status and tests).
  pending(): number
  // Resolves every waiter with a timeout and forgets everything (kill switch, dispose).
  cancelAll(): void
}

const keyOf = (t: DomTarget, frame: string): string => ('label_hash' in t ? `h|${t.label_hash}|${frame}` : `r|${t.role}|${t.name}|${frame}`)

export function createDomGrounder(opts: DomGrounderOptions = {}): DomGrounder {
  const now = opts.now ?? Date.now
  const setT = opts.setTimer ?? ((fn, ms) => setTimeout(fn, ms))
  const clearT = opts.clearTimer ?? ((h) => clearTimeout(h as ReturnType<typeof setTimeout>))
  const newId = opts.id ?? (() => `rq_${randomUUID().replace(/-/g, '').slice(0, 20)}`)
  const reissueMs = opts.reissueMs ?? 2500
  const queue: Pending[] = []

  const settle = (p: Pending, outcome: RequestOutcome): void => {
    const i = queue.indexOf(p)
    if (i >= 0) queue.splice(i, 1)
    clearT(p.timer)
    for (const w of p.waiters.splice(0)) w(outcome)
  }

  return {
    request(target, o = {}) {
      const frame = o.frameId ?? 'top'
      const key = keyOf(target, frame)
      const existing = queue.find((p) => p.key === key)
      const timeoutMs = o.timeoutMs ?? 3000
      return new Promise<RequestOutcome>((resolve) => {
        if (existing) {
          existing.waiters.push(resolve) // the same question asked twice shares one answer
          return
        }
        const p: Pending = { want: wantFor(target, newId(), frame), key, issuedAt: null, deadline: now() + timeoutMs, waiters: [resolve], timer: null }
        p.timer = setT(() => settle(p, { kind: 'timeout' }), timeoutMs)
        queue.push(p)
      })
    },
    nextWant() {
      const t = now()
      const p = queue.find((q) => q.issuedAt === null || t - q.issuedAt >= reissueMs)
      if (!p) return null
      p.issuedAt = t
      return p.want
    },
    answer(a) {
      const p = queue.find((q) => q.want.request_id === a.request_id)
      if (!p) return false // late, or never asked
      settle(p, { kind: 'answer', answer: a, receivedAt: now() })
      return true
    },
    pending: () => queue.length,
    cancelAll() {
      for (const p of [...queue]) settle(p, { kind: 'timeout' })
    },
  }
}

// ---------- following one target ----------
export type HideReason = MapFailure | 'stale' | 'no_answer'

export interface TrackCallbacks {
  onVisible(box: NormBox, info: { scroll: XY | undefined; ageMs: number; moved: boolean }): void
  onHidden(reason: HideReason): void
}

export interface TrackOptions {
  display: () => DisplayInfo
  calibration?: XY
  // Pause between answers. The extension answers back to back, so this sets how often the ring is refreshed.
  refreshMs?: number
  // Hide when the newest good answer is older than this (the extension stopped answering, or the page changed under it).
  staleMs?: number
  // One request's patience.
  requestTimeoutMs?: number
  now?: () => number
  setTimer?: (fn: () => void, ms: number) => unknown
  clearTimer?: (h: unknown) => void
  log?: (scope: string, ...args: unknown[]) => void
}

export interface Tracker {
  stop(): void
  // The last thing that was reported: visible with a box, or hidden with a reason.
  state(): { visible: boolean; reason?: HideReason }
}

/** Follows `target` until stopped. Reports only changes in visibility, and every move of the box while visible. */
export function trackTarget(grounder: Pick<DomGrounder, 'request'>, target: DomTarget, cb: TrackCallbacks, opts: TrackOptions): Tracker {
  const now = opts.now ?? Date.now
  const setT = opts.setTimer ?? ((fn, ms) => setTimeout(fn, ms))
  const clearT = opts.clearTimer ?? ((h) => clearTimeout(h as ReturnType<typeof setTimeout>))
  const refreshMs = opts.refreshMs ?? 250
  const staleMs = opts.staleMs ?? 1500
  const reqMs = opts.requestTimeoutMs ?? 1500
  let stopped = false
  let visible = false
  let lastReason: HideReason | undefined
  let lastScroll: XY | undefined
  let loopTimer: unknown = null
  let staleTimer: unknown = null

  const hide = (reason: HideReason): void => {
    if (stopped) return
    if (!visible && lastReason === reason) return
    visible = false
    lastReason = reason
    cb.onHidden(reason)
  }
  const armStale = (): void => {
    if (staleTimer !== null) clearT(staleTimer)
    staleTimer = setT(() => {
      // No good answer for staleMs: whatever is drawn is out of date. Hide it; the loop keeps asking and redraws on the next good one.
      if (visible) hide('stale')
    }, staleMs)
  }

  const step = async (): Promise<void> => {
    if (stopped) return
    const out = await grounder.request(target, { timeoutMs: reqMs })
    if (stopped) return
    if (out.kind === 'timeout') {
      if (!visible && lastReason === undefined) hide('no_answer')
    } else {
      const age = ageNow(out.answer, out.receivedAt, now())
      const mapped: Mapped = mapAnswer(out.answer, { display: opts.display(), calibration: opts.calibration })
      if (!mapped.ok) hide(mapped.reason)
      else if (age > staleMs) hide('stale')
      else {
        const moved = !visible || !lastScroll || !out.answer.scroll || Math.abs(lastScroll.x - out.answer.scroll.x) >= 1 || Math.abs(lastScroll.y - out.answer.scroll.y) >= 1
        visible = true
        lastReason = undefined
        lastScroll = out.answer.scroll
        armStale()
        cb.onVisible(mapped.norm, { scroll: out.answer.scroll, ageMs: age, moved })
      }
    }
    if (!stopped) loopTimer = setT(() => void step(), refreshMs)
  }
  void step()

  return {
    stop() {
      stopped = true
      if (loopTimer !== null) clearT(loopTimer)
      if (staleTimer !== null) clearT(staleTimer)
    },
    state: () => ({ visible, ...(lastReason ? { reason: lastReason } : {}) }),
  }
}
