// Pinned views: Genome ("Where time goes"), Graph ("How work connects") and Presence ("Your hours") in the sidebar under "Look closer".
// Off by default; Settings, Views, "Pinned views" switches it on (Track C draws that row and calls setPinnedViews). Remembered on this device.
import { useSyncExternalStore } from "react";

export const PINNED_KEY = "understudy-pinned-views";

function read(): boolean {
  try { return window.localStorage.getItem(PINNED_KEY) === "1"; } catch { return false; }
}

let on = typeof window === "undefined" ? false : read();
const listeners = new Set<() => void>();

export const getPinnedViews = (): boolean => on;

export function setPinnedViews(next: boolean): void {
  if (next === on) return;
  on = next;
  try { if (next) window.localStorage.setItem(PINNED_KEY, "1"); else window.localStorage.removeItem(PINNED_KEY); } catch { /* storage can be blocked */ }
  listeners.forEach((l) => l());
}

export function usePinnedViews(): [boolean, (v: boolean) => void] {
  const v = useSyncExternalStore((cb) => { listeners.add(cb); return () => listeners.delete(cb); }, () => on, () => false);
  return [v, setPinnedViews];
}
