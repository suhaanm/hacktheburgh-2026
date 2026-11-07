// Coach telemetry: coach_shown / coach_followed / coach_dismissed events for the intervention policy (ANA-6) and the "false nudges
// per hour" report (COA-4). The desktop only reports what happened and how long it took; the engine decides what it means.
//   shown      a guidance ring (point-, runner-, dom- ids) was drawn
//   followed   the step was verified (a tick, or a lesson:step 'verified')
//   dismissed  the ring was cleared without the step being verified (Stop, kill, a lesson that ended, a screen change)
// A clear that is immediately followed by a new ring is a replacement, not a dismissal (point_at clears before it draws).
import type { OverlayController } from '../../shared/contracts'
import type { Annotation } from '../../shared/protocol'
import type { Bus } from '../bus'
import type { EventInput } from './event'

export type CoachDismissHow = 'user' | 'stop' | 'replaced' | 'stale' | 'ended'

export interface CoachTrackerOptions {
  emit: (input: EventInput) => unknown
  now?: () => number
  level?: () => string | null // 'l1'..'l4'
  // A clear is held this long before it counts as a dismissal; a new ring in that time cancels it.
  replaceWindowMs?: number
  // A ring nobody acted on for this long is closed without a label (no event: silence is not a decision).
  staleMs?: number
  setTimer?: (fn: () => void, ms: number) => unknown
  clearTimer?: (h: unknown) => void
}

export interface CoachTracker {
  shown(promptId: string, extra?: { label_hash?: string; domain_hash?: string }): void
  followed(promptId?: string): void
  dismissed(promptId: string | undefined, how: CoachDismissHow): void
  // Called when a clear arrives for these ids: counts as a dismissal unless a ring is drawn within the replace window.
  cleared(ids?: string[]): void
  open(): string[]
  dispose(): void
}

export function createCoachTracker(opts: CoachTrackerOptions): CoachTracker {
  const now = opts.now ?? Date.now
  const replaceMs = opts.replaceWindowMs ?? 150
  const staleMs = opts.staleMs ?? 120_000
  const setT = opts.setTimer ?? ((fn, ms) => setTimeout(fn, ms))
  const clearT = opts.clearTimer ?? ((h) => clearTimeout(h as ReturnType<typeof setTimeout>))
  const openPrompts = new Map<string, { at: number; label_hash?: string; domain_hash?: string }>()
  let pending: unknown = null
  let pendingIds: string[] = []

  const meta = (extra: Record<string, number | string | boolean> = {}): Record<string, number | string | boolean> => {
    const level = opts.level?.()
    return { ...(level && /^l[1-4]$/.test(level) ? { level } : {}), ...extra }
  }
  const target = (p: { label_hash?: string; domain_hash?: string }): EventInput['target'] => ({ role: 'ring', ...(p.label_hash ? { label_hash: p.label_hash } : {}), ...(p.domain_hash ? { domain_hash: p.domain_hash } : {}) })

  const cancelPending = (): void => {
    if (pending !== null) clearT(pending)
    pending = null
    pendingIds = []
  }

  const dismiss = (id: string, how: CoachDismissHow): void => {
    const p = openPrompts.get(id)
    if (!p) return
    openPrompts.delete(id)
    opts.emit({ source: 'coach', type: 'coach_dismissed', target: target(p), meta: meta({ latency_ms: Math.max(0, now() - p.at), how }) })
  }

  const sweep = (): void => {
    for (const [id, p] of openPrompts) if (now() - p.at > staleMs) openPrompts.delete(id)
  }

  return {
    shown(promptId, extra = {}) {
      sweep()
      cancelPending() // a ring drawn right after a clear: the clear was a replacement
      if (openPrompts.has(promptId)) return // the same ring redrawn: not a new prompt
      openPrompts.set(promptId, { at: now(), ...extra })
      opts.emit({ source: 'coach', type: 'coach_shown', target: target(extra), meta: meta() })
    },
    followed(promptId) {
      const ids = promptId ? [promptId] : [...openPrompts.keys()]
      for (const id of ids) {
        const p = openPrompts.get(id)
        if (!p) continue
        openPrompts.delete(id)
        opts.emit({ source: 'coach', type: 'coach_followed', target: target(p), meta: meta({ latency_ms: Math.max(0, now() - p.at) }) })
      }
    },
    dismissed(promptId, how) {
      cancelPending()
      const ids = promptId ? [promptId] : [...openPrompts.keys()]
      for (const id of ids) dismiss(id, how)
    },
    cleared(ids) {
      const targets = (ids ?? [...openPrompts.keys()]).filter((id) => openPrompts.has(id))
      if (targets.length === 0) return
      cancelPending()
      pendingIds = targets
      pending = setT(() => {
        const t = pendingIds
        pending = null
        pendingIds = []
        for (const id of t) dismiss(id, 'user')
      }, replaceMs)
    },
    open: () => [...openPrompts.keys()],
    dispose: cancelPending,
  }
}

const RING_PREFIXES = ['point-', 'runner-', 'dom-']
const isRing = (a: Annotation): boolean => a.kind === 'ring' && RING_PREFIXES.some((p) => a.id.startsWith(p))

/** Wraps an OverlayController so what it draws and clears is reported as coach events. The wrapped controller is untouched. */
export function withCoachTelemetry(overlay: OverlayController, tracker: CoachTracker): OverlayController {
  return {
    show(annotations) {
      overlay.show(annotations)
      for (const a of annotations) {
        if (isRing(a)) tracker.shown(a.id)
        else if (a.kind === 'tick' && a.ok) tracker.followed()
      }
    },
    clear(ids) {
      overlay.clear(ids)
      tracker.cleared(ids)
    },
    caption: (speaker, text, final) => overlay.caption(speaker, text, final),
    chip: (level, label) => overlay.chip(level, label),
  }
}

export type CoachBus = Pick<Bus, 'on'>

/** lesson:step verified -> followed; a lesson that aborts or a session that ends by Stop/error -> dismissed. Returns the undo. */
export function wireCoachBus(bus: CoachBus, tracker: CoachTracker): () => void {
  const offStep = bus.on('lesson:step', (e) => {
    if (e.phase === 'verified' || e.phase === 'done') tracker.followed()
    else if (e.phase === 'aborted') tracker.dismissed(undefined, 'ended')
  })
  const offEnd = bus.on('session:ended', ({ reason }) => {
    if (reason === 'stop' || reason === 'error') tracker.dismissed(undefined, 'stop')
  })
  return () => {
    offStep()
    offEnd()
  }
}
