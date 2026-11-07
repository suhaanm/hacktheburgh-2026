// Appearance: Auto, Light or Dark. One small store so the account menu, Settings (Appearance) and the shell all read the same choice.
// The storage key keeps its old name (it is an internal identifier). Storage can be blocked, so every read and write is guarded.
import { useSyncExternalStore } from "react";

export type Theme = "auto" | "light" | "dark";
export const THEME_KEY = "understudy-theme";
export const THEME_LABEL: Record<Theme, string> = { auto: "Auto", light: "Light", dark: "Dark" };
export const THEMES: Theme[] = ["auto", "light", "dark"];

function load(): Theme {
  try {
    const t = window.localStorage.getItem(THEME_KEY);
    if (t === "light" || t === "dark") return t;
  } catch { /* storage can be blocked */ }
  return "auto";
}

let current: Theme = typeof window === "undefined" ? "auto" : load();
const listeners = new Set<() => void>();

function apply(t: Theme): void {
  if (typeof document === "undefined") return;
  if (t === "auto") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.setAttribute("data-theme", t);
}

/** Apply the remembered theme once at start-up. */
export function initTheme(): void { apply(current); }

export const getTheme = (): Theme => current;

export function setTheme(t: Theme): void {
  if (!THEMES.includes(t) || t === current) return;
  current = t;
  apply(t);
  try { window.localStorage.setItem(THEME_KEY, t); } catch { /* ignore */ }
  listeners.forEach((l) => l());
}

export function useTheme(): [Theme, (t: Theme) => void] {
  const t = useSyncExternalStore((cb) => { listeners.add(cb); return () => listeners.delete(cb); }, () => current, () => "auto" as Theme);
  return [t, setTheme];
}
