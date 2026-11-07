// A ring on a real browser element. The target comes from the coach brain (GET /coach/next, addressed by capture ZONE) or from a
// local process (POST /coach/ring). The ring is drawn from what the extension measured, follows scrolling (re-resolved every few
// hundred ms) and is hidden at once when the element is gone, scrolled out of view, in a frame this app cannot place, or the
// answers stop (COA-6). Hiding is not a dismissal: the ring comes back when the element is found again. The nudge text, when there
// is one, sits in a bubble above the ring. Coach telemetry (shown, followed, dismissed) is reported here, and `onEnd` tells the
// caller how a prompt ended so the worker's response can be posted to /coach/feedback.
import type { OverlayController } from '../../shared/contracts'
import type { Annotation } from '../../shared/protocol'
import type { CoachDismissHow, CoachTracker } from '../engine/coach-events'
import { trackTarget, type DomGrounder, type HideReason, type Tracker } from './dom-grounder'
import type { DomTarget } from './protocol'
import type { DisplayInfo } from './rect-map'
import type { XY } from './protocol'

export const DOM_RING_ID = 'dom-ring'
export const DOM_BUBBLE_ID = 'dom-bubble'
const MESSAGE_MAX = 160

export interface DomPromptEnd {
  // What the caller tagged the prompt with (the coach brain's decision id).
  ref: string | undefined
  how: CoachDismissHow | 'followed'
  // The worker actually saw the ring at some point. A prompt that was never drawn has no outcome.
  shown: boolean
}

export interface DomCoachDeps {
  grounder: Pick<DomGrounder, 'request'>
  overlay: Pick<OverlayController, 'show' | 'clear'>
  display: () => DisplayInfo
  tracker?: Pick<CoachTracker, 'shown' | 'followed' | 'dismissed'>
  calibration?: XY
  // A ring nobody acts on goes away after this long.
  ttlMs?: number
  refreshMs?: number
  staleMs?: number
  onEnd?: (e: DomPromptEnd) => void
  now?: () => number
  setTimer?: (fn: () => void, ms: number) => unknown
  clearTimer?: (h: unknown) => void
  log?: (scope: string, ...args: unknown[]) => void
}

export interface DomCoachState {
  target: DomTarget
  label?: string
  message?: string
  ref?: string
  visible: boolean
  hiddenFor?: HideReason
}

export interface PointOptions {
  label?: string
  step?: number
  // The coaching text, shown in a bubble above the ring.
  message?: string
  // Tag for the caller (the brain's decision id), handed back in onEnd.
  ref?: string
}

export interface DomCoach {
  point(target: DomTarget, o?: PointOptions): void
  // Remove the ring. `how` is what happened to the prompt (default: the worker or the system cleared it).
  clear(how?: CoachDismissHow): void
  // The step the ring pointed at was done.
  followed(): void
  current(): DomCoachState | null
  dispose(): void
}

const sameTarget = (a: DomTarget, b: DomTarget): boolean => JSON.stringify(a) === JSON.stringify(b)
const clean = (s: string | undefined): string | undefined => {
  const t = s?.replace(/\s+/g, ' ').trim().slice(0, MESSAGE_MAX)
  return t ? t : undefined
}

export function createDomCoach(deps: DomCoachDeps): DomCoach {
  const setT = deps.setTimer ?? ((fn, ms) => setTimeout(fn, ms))
  const clearT = deps.clearTimer ?? ((h) => clearTimeout(h as ReturnType<typeof setTimeout>))
  const log = deps.log ?? (() => undefined)
  const ttlMs = deps.ttlMs ?? 90_000
  let active: { target: DomTarget; label?: string; step?: number; message?: string; ref?: string; tracker: Tracker; ttl: unknown; visible: boolean; hiddenFor?: HideReason; reported: boolean } | null = null

  const telemetry = (t: DomTarget): { label_hash?: string; zone?: string } => ('label_hash' in t ? { label_hash: t.label_hash } : 'zone' in t ? { zone: t.zone } : {})

  const end = (how: CoachDismissHow | 'followed'): void => {
    const a = active
    if (!a) return
    active = null
    a.tracker.stop()
    clearT(a.ttl)
    deps.overlay.clear([DOM_RING_ID, DOM_BUBBLE_ID])
    if (a.reported) {
      if (how === 'followed') deps.tracker?.followed(DOM_RING_ID)
      else deps.tracker?.dismissed(DOM_RING_ID, how)
    }
    try {
      deps.onEnd?.({ ref: a.ref, how, shown: a.reported })
    } catch (err) {
      log('dom-coach', `onEnd failed: ${err instanceof Error ? err.message : String(err)}`)
    }
  }

  return {
    point(target, o = {}) {
      if (active && sameTarget(active.target, target)) {
        // The same element again (the brain is polled): keep following it; the text, the label and the tag may change.
        active.label = o.label ?? active.label
        active.step = o.step ?? active.step
        active.message = clean(o.message) ?? active.message
        active.ref = o.ref ?? active.ref
        return
      }
      if (active) end('replaced')
      const state = { target, label: o.label, step: o.step, message: clean(o.message), ref: o.ref, tracker: null as unknown as Tracker, ttl: null as unknown, visible: false, hiddenFor: undefined as HideReason | undefined, reported: false }
      active = state
      state.ttl = setT(() => end('stale'), ttlMs)
      state.tracker = trackTarget(
        deps.grounder,
        target,
        {
          onVisible: (box) => {
            if (active !== state) return
            state.visible = true
            state.hiddenFor = undefined
            const marks: Annotation[] = [{ id: DOM_RING_ID, kind: 'ring', tone: 'guide', box, ...(state.label ? { label: state.label } : {}), ...(state.step ? { step: state.step } : {}) }]
            if (state.message) marks.push({ id: DOM_BUBBLE_ID, kind: 'bubble', tone: 'guide', at: { x: (box.xmin + box.xmax) / 2, y: box.ymin }, text: state.message })
            deps.overlay.show(marks)
            if (!state.reported) {
              state.reported = true
              deps.tracker?.shown(DOM_RING_ID, telemetry(target))
            }
          },
          onHidden: (reason) => {
            if (active !== state) return
            state.visible = false
            state.hiddenFor = reason
            deps.overlay.clear([DOM_RING_ID, DOM_BUBBLE_ID])
            log('dom-coach', `ring hidden (${reason})`)
          },
        },
        { display: deps.display, calibration: deps.calibration, refreshMs: deps.refreshMs, staleMs: deps.staleMs, now: deps.now, setTimer: deps.setTimer, clearTimer: deps.clearTimer },
      )
    },
    clear: (how = 'user') => end(how),
    followed: () => end('followed'),
    current: () =>
      active
        ? { target: active.target, ...(active.label ? { label: active.label } : {}), ...(active.message ? { message: active.message } : {}), ...(active.ref ? { ref: active.ref } : {}), visible: active.visible, ...(active.hiddenFor ? { hiddenFor: active.hiddenFor } : {}) }
        : null,
    dispose: () => end('stale'),
  }
}
