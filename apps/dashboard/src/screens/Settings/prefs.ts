// Dashboard preferences kept on this device: the theme and Pinned views. Storage can be blocked, so every read and write is guarded and the page
// still renders. A tiny external store, like components/home/viewAs.ts, so the shell can read Pinned views without a provider.
import { useSyncExternalStore } from "react";
import { THEME_KEY, themeOf, type Theme } from "./model";

export const PINNED_KEY = "understudy-pinned-views";

function read(key: string): string | null { try { return window.localStorage.getItem(key); } catch { return null; } }
function write(key: string, v: string | null): void { try { if (v === null) window.localStorage.removeItem(key); else window.localStorage.setItem(key, v); } catch { /* blocked: lasts until reload */ } }

export function getTheme(): Theme { return themeOf(read(THEME_KEY)); }
/** `auto` follows the system; light and dark are the worker's own choice. */
export function applyTheme(t: Theme): void {
  if (typeof document === "undefined") return;
  if (t === "auto") document.documentElement.removeAttribute("data-theme"); else document.documentElement.setAttribute("data-theme", t);
}
export function setTheme(t: Theme): void { applyTheme(t); write(THEME_KEY, t === "auto" ? null : t); }

const listeners = new Set<() => void>();
let pinned = typeof window === "undefined" ? false : read(PINNED_KEY) === "1";
export const getPinned = (): boolean => pinned;
export function setPinned(on: boolean): void {
  if (on === pinned) return;
  pinned = on;
  write(PINNED_KEY, on ? "1" : null);
  listeners.forEach((l) => l());
}
export function usePinned(): boolean {
  return useSyncExternalStore((cb) => { listeners.add(cb); return () => listeners.delete(cb); }, () => pinned, () => false);
}
