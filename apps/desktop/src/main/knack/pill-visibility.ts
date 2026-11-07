// Whether the corner pill may be on screen right now, and where. Pure; pill-window.ts applies the answer.
//
// Never over a secure input (a password field has focus), never over a denylisted app, hidden while the screen is shared or a presentation runs, and out of
// the way when Knack itself is the app in front. The same probes the awareness and Cue layers use (awareness/probes.ts, awareness/denylist.ts, through
// cue-glue.ts createCueSignals) decide the first two; strict mode reads an app or secure-input state it cannot read as "stay away".
import type { PillKind } from './pill-state'
import type { DisplayLike, Rect, Size } from './window-bounds'
import { displayAtPoint } from './window-bounds'

export const PILL_SIZE: Size = { width: 280, height: 44 }
export const PILL_MARGIN = 16
export const PILL_OPACITY = 0.85

export type HideReason = 'idle' | 'disabled' | 'suppressed' | 'presenting' | 'knack_in_front' | 'killed_off'

export interface PillVisibilityInput {
  kind: PillKind
  /** The Cue-signals reason to stay away (a denylisted app, secure input, an unreadable state); null when none. */
  suppressed: string | null
  /** Screen sharing, or a presentation or full-screen show is running. */
  presenting: boolean
  /** The main window is up and is the front app: it shows the same state itself. */
  knackInFront: boolean
  /** The shell is off (headless, no overlay). */
  disabled: boolean
}

export function pillVisibility(i: PillVisibilityInput): { show: boolean; reason: HideReason | null } {
  if (i.disabled) return { show: false, reason: 'disabled' }
  if (i.kind === 'idle') return { show: false, reason: 'idle' }
  // Safety first: these win over everything, the Stopped state included.
  if (i.suppressed !== null) return { show: false, reason: 'suppressed' }
  if (i.presenting) return { show: false, reason: 'presenting' }
  if (i.knackInFront) return { show: false, reason: 'knack_in_front' }
  return { show: true, reason: null }
}

/** Bottom-right of the work area, above the Dock, with a margin. */
export function pillBounds(workArea: Rect, size: Size = PILL_SIZE, margin = PILL_MARGIN): Rect {
  return { x: workArea.x + workArea.width - size.width - margin, y: workArea.y + workArea.height - size.height - margin, width: size.width, height: size.height }
}

/** The display where the work is happening: the one the pointer is on (an agent that acts moves it), else the primary. */
export function workDisplay<D extends DisplayLike>(displays: readonly D[], pointer: { x: number; y: number }, primary: D): D {
  return displayAtPoint(displays, pointer) ?? primary
}

/**
 * Which parts of the pill take the pointer; the rest lets clicks through to the app underneath. The Stop button while something works, and the
 * label (to open Knack) in every state that has one. Nothing else: the glyph and the padding never block a click.
 */
export function interactiveParts(kind: PillKind): { stop: boolean; open: boolean } {
  if (kind === 'idle') return { stop: false, open: false }
  return { stop: kind === 'working', open: true }
}
