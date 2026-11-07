// The one-voice lock (REQ-8, docs/ATTENTION_DESIGN.md section 8.2): while a cue, a question card or a toast is up, nothing else interrupts.
// A tiny module with a synchronous answer and a mandatory time-to-live, so a holder that crashes or forgets to release can never block
// everything: the lock simply runs out.
//
// Who may take it from whom: only safety preempts a holder (a kill, an injection pause, an irreversible decision outrank everything on
// screen), and the worker's own ask ("asked": a cue they pressed for) preempts the lighter holders. Anything else waits its turn; waiting
// is cheap because a display lasts seconds.
export type LockOwner = 'safety' | 'asked' | 'decision' | 'cue' | 'notice' | 'glance'

/** Which owners each owner may preempt. Same owner, or anything not listed, loses to the holder. */
export const PREEMPTS: Readonly<Record<LockOwner, readonly LockOwner[]>> = {
  safety: ['asked', 'decision', 'cue', 'notice', 'glance'],
  asked: ['cue', 'notice', 'glance'],
  decision: [],
  cue: [],
  notice: [],
  glance: [],
}

export interface LockHolder {
  owner: LockOwner
  /** What the holder is showing (an item id, an episode id): the same owner showing the same thing is a continuation, a different thing waits. */
  key: string
  until: number
}

export interface VoiceLock {
  /** Take the lock for `ttlMs`. True when it is now yours. `onPreempt` is called if a stronger owner takes it from you: hide at once.
   *  `key` names what you are showing; asking again with the same owner and key is a continuation, with another key it waits. */
  acquire(owner: LockOwner, ttlMs: number, onPreempt?: () => void, key?: string): boolean
  /** Give the lock back. A no-op if you no longer hold it (or, with a key, if it is holding something else). */
  release(owner: LockOwner, key?: string): void
  holder(): LockHolder | null
  /** Would `acquire` succeed right now? (no side effect) */
  available(owner: LockOwner, key?: string): boolean
  /** Make the lock last longer (a continuation of the same display). A no-op if you do not hold it. */
  extend(owner: LockOwner, ttlMs: number, key?: string): void
}

export function createVoiceLock(now: () => number = Date.now): VoiceLock {
  let held: { owner: LockOwner; key: string; until: number; onPreempt?: () => void } | null = null
  const live = () => {
    if (held && held.until <= now()) held = null // the time-to-live ran out: nobody can wedge the lock
    return held
  }
  const ttl = (ms: number) => (Number.isFinite(ms) && ms > 0 ? Math.min(ms, 120_000) : 1_000)
  return {
    acquire(owner, ttlMs, onPreempt, key = owner) {
      const cur = live()
      if (cur && cur.owner === owner && cur.key === key) {
        held = { owner, key, until: now() + ttl(ttlMs), onPreempt: onPreempt ?? cur.onPreempt }
        return true // the same owner still showing the same thing: a continuation
      }
      if (cur) {
        if (!PREEMPTS[owner].includes(cur.owner)) return false
        const cb = cur.onPreempt
        held = null
        try {
          cb?.()
        } catch {
          // a holder that throws while hiding must not keep the voice
        }
      }
      held = { owner, key, until: now() + ttl(ttlMs), onPreempt }
      return true
    },
    release(owner, key) {
      if (held && held.owner === owner && (key === undefined || held.key === key)) held = null
    },
    holder() {
      const cur = live()
      return cur ? { owner: cur.owner, key: cur.key, until: cur.until } : null
    },
    available(owner, key = owner) {
      const cur = live()
      return !cur || (cur.owner === owner && cur.key === key) || PREEMPTS[owner].includes(cur.owner)
    },
    extend(owner, ttlMs, key) {
      const cur = live()
      if (cur && cur.owner === owner && (key === undefined || cur.key === key)) cur.until = Math.max(cur.until, now() + ttl(ttlMs))
    },
  }
}

/**
 * Wait up to `maxWaitMs` for the voice, then give up (false). For a surface that must not be lost, such as a permission prompt: it waits a
 * moment for a cue to finish (a cue lasts about 12 s, so a short wait is usually enough) and the caller draws anyway when this answers false.
 */
export function acquireWithin(
  lock: VoiceLock,
  owner: LockOwner,
  ttlMs: number,
  maxWaitMs: number,
  key?: string,
  onPreempt?: () => void,
  opts: { pollMs?: number; now?: () => number; sleep?: (ms: number) => Promise<void> } = {},
): Promise<boolean> {
  const now = opts.now ?? Date.now
  const sleep = opts.sleep ?? ((ms: number) => new Promise<void>((r) => setTimeout(r, ms)))
  const poll = opts.pollMs ?? 100
  const deadline = now() + Math.max(0, maxWaitMs)
  const step = async (): Promise<boolean> => {
    if (lock.acquire(owner, ttlMs, onPreempt, key)) return true
    if (now() >= deadline) return false
    await sleep(poll)
    return step()
  }
  return step()
}
