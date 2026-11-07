// A ring on a real browser element. The target comes from the engine's coach state, or from a local process (POST /coach/ring).
// The ring is drawn from what the extension measured, follows scrolling (re-resolved every few hundred ms) and is hidden at once
// when the element is gone, scrolled out of view, in a frame this app cannot place, or the answers stop (COA-6). Hiding is not a
// dismissal: the ring comes back when the element is found again. Coach telemetry (shown, followed, dismissed) is reported here.
import type { OverlayController } from '../../shared/contracts'
import type { CoachDismissHow, CoachTracker } from '../engine/coach-events'
import { trackTarget, type DomGrounder, type HideReason, type Tracker } from './dom-grounder'
import type { DomTarget } from './protocol'
import type { DisplayInfo } from './rect-map'
import type { XY } from './protocol'

export const DOM_RING_ID = 'dom-ring'

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
  now?: () => number
  setTimer?: (fn: () => void, ms: number) => unknown
  clearTimer?: (h: unknown) => void
  log?: (scope: string, ...args: unknown[]) => void
}

export interface DomCoachState {
  target: DomTarget
  label?: string
  visible: boolean
  hiddenFor?: HideReason
}

export interface DomCoach {
  point(target: DomTarget, o?: { label?: string; step?: number }): void
  // Remove the ring. `how` is what happened to the prompt (default: the worker or the system cleared it).
  clear(how?: CoachDismissHow): void
  // The step the ring pointed at was done.
  followed(): void
  current(): DomCoachState | null
  dispose(): void
}

const sameTarget = (a: DomTarget, b: DomTarget): boolean => JSON.stringify(a) === JSON.stringify(b)

export function createDomCoach(deps: DomCoachDeps): DomCoach {
  const setT = deps.setTimer ?? ((fn, ms) => setTimeout(fn, ms))
  const clearT = deps.clearTimer ?? ((h) => clearTimeout(h as ReturnType<typeof setTimeout>))
  const log = deps.log ?? (() => undefined)
  const ttlMs = deps.ttlMs ?? 90_000
  let active: { target: DomTarget; label?: string; step?: number; tracker: Tracker; ttl: unknown; visible: boolean; hiddenFor?: HideReason; reported: boolean } | null = null

  const labelHash = (t: DomTarget): { label_hash?: string } => ('label_hash' in t ? { label_hash: t.label_hash } : {})

  const end = (how: CoachDismissHow | 'followed'): void => {
    const a = active
    if (!a) return
    active = null
    a.tracker.stop()
    clearT(a.ttl)
    deps.overlay.clear([DOM_RING_ID])
    if (a.reported) {
      if (how === 'followed') deps.tracker?.followed(DOM_RING_ID)
      else deps.tracker?.dismissed(DOM_RING_ID, how)
    }
  }

  return {
    point(target, o = {}) {
      if (active && sameTarget(active.target, target)) {
        // The same element again (the coach state is polled): keep following it, only the label may change.
        active.label = o.label ?? active.label
        active.step = o.step ?? active.step
        return
      }
      if (active) end('replaced')
      const state = { target, label: o.label, step: o.step, tracker: null as unknown as Tracker, ttl: null as unknown, visible: false, hiddenFor: undefined as HideReason | undefined, reported: false }
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
            deps.overlay.show([{ id: DOM_RING_ID, kind: 'ring', tone: 'guide', box, ...(state.label ? { label: state.label } : {}), ...(state.step ? { step: state.step } : {}) }])
            if (!state.reported) {
              state.reported = true
              deps.tracker?.shown(DOM_RING_ID, labelHash(target))
            }
          },
          onHidden: (reason) => {
            if (active !== state) return
            state.visible = false
            state.hiddenFor = reason
            deps.overlay.clear([DOM_RING_ID])
            log('dom-coach', `ring hidden (${reason})`)
          },
        },
        { display: deps.display, calibration: deps.calibration, refreshMs: deps.refreshMs, staleMs: deps.staleMs, now: deps.now, setTimer: deps.setTimer, clearTimer: deps.clearTimer },
      )
    },
    clear: (how = 'user') => end(how),
    followed: () => end('followed'),
    current: () => (active ? { target: active.target, ...(active.label ? { label: active.label } : {}), visible: active.visible, ...(active.hiddenFor ? { hiddenFor: active.hiddenFor } : {}) } : null),
    dispose: () => end('stale'),
  }
}
