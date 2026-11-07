// Which overlay is open: the command palette, the guided tour (and its step), the Settings sheet, or the "About this screen" panel.
// In memory only, like viewAs.ts: a reload closes them all. At most one is open at a time (one interrupting surface, docs/KNACK_UX.md).
// The tour never starts by itself. It starts from the palette entry "Take the tour" or from the account menu, both through startTour().
import { useSyncExternalStore } from "react";

export interface OverlayState {
  palette: boolean;
  tour: { step: number } | null;
  /** The Settings sheet; `section` is the row to scroll to (live-models, interruptions, coaching, ...), or null for the top. */
  settings: { section: string | null } | null;
  /** The "About this screen" side panel. */
  about: boolean;
}

const CLOSED: OverlayState = { palette: false, tour: null, settings: null, about: false };
let state: OverlayState = CLOSED;
const listeners = new Set<() => void>();

/** Where focus returns when the tour ends: the element that had it when the tour started. */
let tourReturn: HTMLElement | null = null;

function set(next: OverlayState): void {
  state = next;
  listeners.forEach((l) => l());
}

export const getOverlay = (): OverlayState => state;

export function openPalette(): void { if (!state.palette) set({ ...CLOSED, palette: true }); }
export function closePalette(): void { if (state.palette) set({ ...state, palette: false }); }
export function togglePalette(): void { set(state.palette ? { ...state, palette: false } : { ...CLOSED, palette: true }); }

/** Open the Settings sheet at a section. Closes the palette, the tour and the About panel: only one thing speaks at a time. */
export function openSettings(section: string | null = null): void { set({ ...CLOSED, settings: { section } }); }
export function closeSettings(): void { if (state.settings) set({ ...state, settings: null }); }

export function openAbout(): void { if (!state.about) set({ ...CLOSED, about: true }); }
export function closeAbout(): void { if (state.about) set({ ...state, about: false }); }
export function toggleAbout(): void { if (state.about) closeAbout(); else openAbout(); }

/** Start the tour at a step (0 by default). Closes everything else. */
export function startTour(step = 0): void {
  tourReturn = typeof document !== "undefined" && document.activeElement instanceof HTMLElement ? document.activeElement : null;
  set({ ...CLOSED, tour: { step: Math.max(0, Math.floor(step)) } });
}

export function setTourStep(step: number): void {
  if (!state.tour) return;
  const s = Math.max(0, Math.floor(step));
  if (s !== state.tour.step) set({ ...state, tour: { step: s } });
}

export function endTour(): void { if (state.tour) set({ ...state, tour: null }); }

/** Take the element focus should return to, once. */
export function takeTourReturn(): HTMLElement | null { const el = tourReturn; tourReturn = null; return el; }

export function useOverlay(): OverlayState {
  return useSyncExternalStore(
    (cb) => { listeners.add(cb); return () => listeners.delete(cb); },
    () => state,
    () => state,
  );
}

/** For tests: close everything. */
export function resetOverlay(): void { tourReturn = null; set(CLOSED); }
