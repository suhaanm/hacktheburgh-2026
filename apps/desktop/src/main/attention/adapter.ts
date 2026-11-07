// The desktop adapter of the attention layer (REQ-8, docs/ATTENTION_DESIGN.md section 8.2). It polls GET /attention/next with the worker's
// signals, draws what the engine says through ports (the existing toast and tray primitives are bound by the shell, not edited here), holds the
// local one-voice lock, and sends the worker's reaction back as feedback. It decides nothing: whether, where, when and how loudly are the
// router's, in the engine. This side only obeys, and refuses to draw anything it cannot draw without breaking the one-voice rule.
//
// Also here: the `AttentionPort` Cue asks before it draws a new cue, question or offer (admission is a synchronous answer from the engine,
// and fails closed), and `report`, how any producer in the desktop tells the layer something.
import { createVoiceLock, type LockOwner, type VoiceLock } from './lock'
import { toStateBody, type AttentionSignals } from './signals'
import { toSubject, type ActionId, type AttentionBadges, type AttentionEvent, type AttentionItem, type EventType, EMPTY_BADGES } from './types'
import type { AttentionClient, FeedbackEvent } from './client'

export interface NoticeView {
  id: string
  type: EventType
  title: string
  body: string
  source: string
  channel: 'toast' | 'chip' | 'question_card' | 'voice' | 'banner' | 'badge'
  actions: Array<{ id: ActionId; label: string }>
  displayMs: number
  priority: number
  reminder: boolean
  preempt: boolean
}

/** What the shell binds to the real surfaces. Every method must be cheap and must not throw. */
export interface AttentionPorts {
  /** Draw a compact notice (top right, never takes focus). The shell routes `toast` here; `chip` and `question_card` items are Cue's own and never arrive here. */
  showNotice(n: NoticeView): void
  hideNotice(id: string): void
  /** The passive counts for the menu bar and the dashboard: needs_you is the tray badge, marker `stopped` is the kill state. */
  setBadges(b: AttentionBadges, digestReady: boolean): void
  /** Open a dashboard page for an action id (the shell maps it to a URL; this side never builds one). */
  open(action: ActionId, item: { id: string; type: EventType }): void
}

export interface AttentionAdapterDeps {
  client: AttentionClient
  signals: () => AttentionSignals
  ports: AttentionPorts
  lock?: VoiceLock
  now?: () => number
  setTimer?: (fn: () => void, ms: number) => unknown
  clearTimer?: (h: unknown) => void
  killed?: () => boolean
  log?: (scope: string, ...args: unknown[]) => void
}

export interface AttentionAdapter {
  readonly lock: VoiceLock
  start(): void
  stop(): void
  /** One poll (the timer calls this; tests and the shell may too). */
  pollOnce(): Promise<void>
  /** The worker pressed a button on a notice, or closed it. */
  action(itemId: string, action: ActionId): void
  closed(itemId: string, how: 'dismissed' | 'timeout'): void
  /** A producer in the desktop reports something. For a cue, use `cuePort().admit`. Never throws. */
  report(ev: AttentionEvent): Promise<void>
  /** What Cue asks before it draws (CueControllerDeps.attention). */
  cuePort(): CueAttentionPort
  /** The 2 s help-level glance asks before it draws. True to draw; the lock is held for the glance and given back by `releaseGlance`. */
  admitGlance(subject: string): Promise<boolean>
  releaseGlance(): void
  current(): { id: string; type: EventType } | null
  badges(): AttentionBadges
}

// Mirrors main/cue/controller.ts `AttentionPort` structurally (that file is Cue's; this one must not import its view types).
export interface CueDecisionLike {
  kind: string
  episode_id: string
  expires_in_s?: number | null
  trigger?: string
}
export interface CueAttentionPort {
  admit(d: CueDecisionLike, onPreempt: () => void): Promise<{ show: boolean; itemId: string | null }>
  release(): void
  feedback(itemId: string, event: 'shown' | 'followed' | 'dismissed' | 'ignored', seconds: number): void
}

const OWNER_BY_PRIORITY: Record<number, LockOwner> = { 3: 'safety', 2: 'decision', 1: 'notice', 0: 'glance' }
const CUE_TYPE: Record<string, 'cue_cue' | 'cue_ask' | 'cue_offer'> = { cue: 'cue_cue', ask: 'cue_ask', offer: 'cue_offer' }
const FOLLOW_ACTIONS = new Set<ActionId>(['open_menu', 'open_run', 'open_queue', 'open_calendar', 'open_routines', 'open_briefing', 'open_report', 'open_settings', 'open_summary'])

export function createAttentionAdapter(deps: AttentionAdapterDeps): AttentionAdapter {
  const now = deps.now ?? Date.now
  const lock = deps.lock ?? createVoiceLock(now)
  const log = deps.log ?? (() => undefined)
  const setTimer = deps.setTimer ?? ((fn: () => void, ms: number) => setTimeout(fn, ms))
  const clearTimer = deps.clearTimer ?? ((h: unknown) => clearTimeout(h as ReturnType<typeof setTimeout>))
  let badges: AttentionBadges = EMPTY_BADGES
  let running = false
  let pollTimer: unknown = null
  let polling = false
  let cur: { item: AttentionItem; owner: LockOwner; shownAt: number; timer: unknown } | null = null

  const clearCur = (): void => {
    if (!cur) return
    clearTimer(cur.timer)
    lock.release(cur.owner, cur.item.id)
    cur = null
  }

  function render(item: AttentionItem): void {
    const owner = OWNER_BY_PRIORITY[item.priority] ?? 'notice'
    if (!lock.acquire(owner, Math.max(1, item.display_s) * 1000, () => hideCurrent('preempted'), item.id)) {
      // Something on screen that this cannot preempt: put the item back so the engine offers it again, and draw nothing.
      void deps.client.feedback(item.id, 'deferred')
      log('attention', 'deferred a notice: the voice is taken')
      return
    }
    const shownAt = now()
    // The engine's channel picks the surface; only a toast is drawn here. A chip or a question card is Cue's own surface and arrives via its port.
    if ((item.channel === 'toast' || item.channel === 'banner') && item.title && item.body) {
      deps.ports.showNotice({
        id: item.id, type: item.type, title: item.title, body: item.body, source: item.source, channel: item.channel, actions: item.actions,
        displayMs: Math.max(1, item.display_s) * 1000, priority: item.priority, reminder: item.reminder, preempt: item.preempt,
      })
    }
    const timer = setTimer(() => {
      if (cur?.item.id === item.id) {
        deps.ports.hideNotice(item.id)
        clearCur() // an untouched display: the engine labels it ignored by itself when its time is up
      }
    }, Math.max(1, item.display_s) * 1000)
    cur = { item, owner, shownAt, timer }
  }

  function hideCurrent(why: string): void {
    if (!cur) return
    log('attention', `notice hidden (${why})`)
    deps.ports.hideNotice(cur.item.id)
    clearCur()
  }

  const secondsSince = (t: number): number => Math.max(0, (now() - t) / 1000)

  async function pollOnce(): Promise<void> {
    if (polling) return
    polling = true
    try {
      const out = await deps.client.next(deps.signals(), now())
      if (!out) return
      badges = out.badges
      deps.ports.setBadges(out.badges, out.digestReady)
      if (out.item) render(out.item)
    } catch (err) {
      log('attention', 'poll failed:', err instanceof Error ? err.message : String(err))
    } finally {
      polling = false
    }
  }

  function schedule(): void {
    if (!running) return
    pollTimer = setTimer(() => {
      void pollOnce().finally(() => schedule())
    }, 2_000)
  }

  const feedbackFor = (action: ActionId): FeedbackEvent | null => (FOLLOW_ACTIONS.has(action) ? 'followed' : action === 'never' ? 'never' : action === 'dismiss' || action === 'not_now' ? 'dismissed' : null)

  return {
    lock,
    start() {
      if (running) return
      running = true
      void pollOnce().finally(() => schedule())
    },
    stop() {
      running = false
      if (pollTimer !== null) clearTimer(pollTimer)
      pollTimer = null
      if (cur) deps.ports.hideNotice(cur.item.id)
      clearCur()
    },
    pollOnce,
    action(itemId, action) {
      if (!cur || cur.item.id !== itemId) return // a stale click on a notice that already left
      const fb = feedbackFor(action)
      const secs = secondsSince(cur.shownAt)
      const { id, type } = cur.item
      if (FOLLOW_ACTIONS.has(action)) deps.ports.open(action, { id, type })
      if (fb) void deps.client.feedback(id, fb, secs)
      hideCurrent(`action ${action}`)
    },
    closed(itemId, how) {
      if (!cur || cur.item.id !== itemId) return
      const secs = secondsSince(cur.shownAt)
      if (how === 'dismissed') void deps.client.feedback(itemId, 'dismissed', secs)
      clearCur() // a timeout needs no feedback: the engine labels it by itself
    },
    async report(ev) {
      try {
        await deps.client.submit({ ...ev, subject: toSubject(ev.subject), state: ev.state ?? toStateBody(deps.signals(), now()) })
      } catch (err) {
        log('attention', 'report failed:', err instanceof Error ? err.message : String(err))
      }
    },
    cuePort() {
      return {
        async admit(d, onPreempt) {
          const type = CUE_TYPE[d.kind]
          if (!type) return { show: false, itemId: null }
          const asked = d.trigger === 'asked'
          const owner: LockOwner = asked ? 'asked' : 'cue'
          const ttl = Math.max(1, d.expires_in_s ?? 20) * 1000
          if (!lock.acquire(owner, ttl, onPreempt, toSubject(d.episode_id))) return { show: false, itemId: null } // something is on screen: the cue's moment passes
          try {
            const res = await deps.client.submit({ type, subject: toSubject(d.episode_id), expires_in_s: Math.max(1, d.expires_in_s ?? 20), asked, state: toStateBody(deps.signals(), now()) })
            if (!res || !res.show) {
              lock.release(owner)
              return { show: false, itemId: res?.itemId ?? null }
            }
            return { show: true, itemId: res.itemId }
          } catch {
            lock.release(owner)
            return { show: false, itemId: null } // fail closed
          }
        },
        release() {
          lock.release('cue')
          lock.release('asked')
        },
        feedback(itemId, event, seconds) {
          if (!itemId) return
          void deps.client.feedback(itemId, event, seconds)
        },
      }
    },
    async admitGlance(subject) {
      const key = toSubject(subject)
      if (!lock.acquire('glance', 3_000, undefined, key)) return false
      try {
        const res = await deps.client.submit({ type: 'help_level_changed', subject: key, expires_in_s: 60, state: toStateBody(deps.signals(), now()) })
        if (res?.show) return true
      } catch {
        // fail closed
      }
      lock.release('glance', key)
      return false
    },
    releaseGlance() {
      lock.release('glance')
    },
    current: () => (cur ? { id: cur.item.id, type: cur.item.type } : null),
    badges: () => badges,
  }
}
