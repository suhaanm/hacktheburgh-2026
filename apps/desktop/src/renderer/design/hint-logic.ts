// The Hint's behaviour as pure functions. Same rules as apps/dashboard/src/components/hint-logic.ts (keep them in step; docs/DESIGN_DIFF.md, D45).
// Open when the pointer is on it, its button has keyboard focus, or a click pinned it, unless it was dismissed (Escape, a second click, a tap elsewhere).

export interface HintState {
  hover: boolean
  focus: boolean
  pinned: boolean
  dismissed: boolean
}

export type HintEvent = 'enter' | 'leave' | 'focus' | 'blur' | 'click' | 'escape' | 'outside'

export const HINT_CLOSED: HintState = { hover: false, focus: false, pinned: false, dismissed: false }

export const isHintOpen = (s: HintState): boolean => !s.dismissed && (s.hover || s.focus || s.pinned)

export function hintReduce(s: HintState, e: HintEvent): HintState {
  switch (e) {
    case 'enter':
      return { ...s, hover: true, dismissed: false }
    case 'leave':
      return { ...s, hover: false }
    case 'focus':
      return { ...s, focus: true, dismissed: false }
    case 'blur':
      return { ...s, focus: false, pinned: false }
    case 'click':
      return s.pinned ? { ...s, pinned: false, dismissed: true } : { ...s, pinned: true, dismissed: false }
    case 'escape':
      return { hover: false, focus: s.focus, pinned: false, dismissed: true }
    case 'outside':
      return { hover: false, focus: false, pinned: false, dismissed: true }
  }
}

export interface Rect {
  left: number
  top: number
  width: number
  height: number
}

/** Centred under the button when it fits, above it when it does not, and never off the screen. */
export function placeHint(btn: Rect, pop: { w: number; h: number }, vp: { w: number; h: number }, margin = 8, gap = 8): { x: number; y: number; side: 'below' | 'above' } {
  const bottom = btn.top + btn.height
  const fitsBelow = bottom + gap + pop.h <= vp.h - margin
  const fitsAbove = btn.top - gap - pop.h >= margin
  const below = fitsBelow || !fitsAbove
  const y = below ? bottom + gap : btn.top - gap - pop.h
  const centred = btn.left + btn.width / 2 - pop.w / 2
  const x = Math.max(margin, Math.min(centred, vp.w - pop.w - margin))
  return { x, y, side: below ? 'below' : 'above' }
}
