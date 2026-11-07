// The Hint's behaviour as pure functions, so a test can read every rule (docs/DESIGN_DIFF.md, D45).
// A Hint is open when the pointer is on it, when its button has keyboard focus, or when it was pinned by a click or tap, unless it was
// dismissed (Escape, a second click, a tap elsewhere). Dismissal lasts until the next enter, focus or click: WCAG 1.4.13 (dismissible).

export interface HintState {
  hover: boolean;
  focus: boolean;
  pinned: boolean;
  dismissed: boolean;
}

export type HintEvent = "enter" | "leave" | "focus" | "blur" | "click" | "escape" | "outside";

export const HINT_CLOSED: HintState = { hover: false, focus: false, pinned: false, dismissed: false };

export const isHintOpen = (s: HintState): boolean => !s.dismissed && (s.hover || s.focus || s.pinned);

export function hintReduce(s: HintState, e: HintEvent): HintState {
  switch (e) {
    case "enter":
      return { ...s, hover: true, dismissed: false };
    case "leave":
      return { ...s, hover: false };
    case "focus":
      return { ...s, focus: true, dismissed: false };
    case "blur":
      // Focus left the button: a pinned note is no longer wanted.
      return { ...s, focus: false, pinned: false };
    case "click":
      // First click or tap pins it open; the next one closes it and keeps it closed until the pointer or focus returns.
      return s.pinned ? { ...s, pinned: false, dismissed: true } : { ...s, pinned: true, dismissed: false };
    case "escape":
      // Escape closes it, keeps focus where it is, and stays closed until the next enter, focus or click.
      return { hover: false, focus: s.focus, pinned: false, dismissed: true };
    case "outside":
      return { hover: false, focus: false, pinned: false, dismissed: true };
  }
}

export interface Rect { left: number; top: number; width: number; height: number }

/** Where the popover goes: centred under the button when it fits, above it when it does not, and never off the screen. */
export function placeHint(btn: Rect, pop: { w: number; h: number }, vp: { w: number; h: number }, margin = 8, gap = 8): { x: number; y: number; side: "below" | "above" } {
  const bottom = btn.top + btn.height;
  const fitsBelow = bottom + gap + pop.h <= vp.h - margin;
  const fitsAbove = btn.top - gap - pop.h >= margin;
  const below = fitsBelow || !fitsAbove;
  const y = below ? bottom + gap : btn.top - gap - pop.h;
  const centred = btn.left + btn.width / 2 - pop.w / 2;
  const x = Math.max(margin, Math.min(centred, vp.w - pop.w - margin));
  return { x, y, side: below ? "below" : "above" };
}
