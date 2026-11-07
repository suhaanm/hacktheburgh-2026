// Which overlay is open: the command palette, or the guided tour (and its step). In memory only, like viewAs.ts: a reload closes both.
// The tour never starts by itself. It starts from the palette entry "Take the tour" or from the help button, both through startTour().
import { useSyncExternalStore } from "react";

export interface OverlayState {
  palette: boolean;
  tour: { step: number } | null;
}

let state: OverlayState = { palette: false, tour: null };
const listeners = new Set<() => void>();

/** Where focus returns when the tour ends: the element that had it when the tour started. */
let tourReturn: HTMLElement | null = null;

function set(next: OverlayState): void {
  state = next;
  listeners.forEach((l) => l());
}

export const getOverlay = (): OverlayState => state;

export function openPalette(): void { if (!state.palette) set({ ...state, palette: true }); }
export function closePalette(): void { if (state.palette) set({ ...state, palette: false }); }
export function togglePalette(): void { set({ ...state, palette: !state.palette }); }

/** Start the tour at a step (0 by default). Closes the palette: only one thing speaks at a time. */
export function startTour(step = 0): void {
  tourReturn = typeof document !== "undefined" && document.activeElement instanceof HTMLElement ? document.activeElement : null;
  set({ palette: false, tour: { step: Math.max(0, Math.floor(step)) } });
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
export function resetOverlay(): void { tourReturn = null; set({ palette: false, tour: null }); }
