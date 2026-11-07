import { useCallback, useEffect, useRef, useState } from "react";
import type { Loaded } from "./api";
import type { AnalyticMeta } from "./types";
import type { Fallback } from "./lib/fallback";

export type LoadState<T> =
  | { status: "loading"; data: T | null; meta: AnalyticMeta | null; source: null; why: Fallback | null; error: null; reload: () => void }
  | { status: "ready"; data: T; meta: AnalyticMeta | null; source: "live" | "demo"; why: Fallback | null; error: null; reload: () => void }
  | { status: "error"; data: T | null; meta: AnalyticMeta | null; source: null; why: Fallback | null; error: Error; reload: () => void };

/** Load a resource; keep the last good data while reloading so screens do not flash empty. */
export function useLoad<T>(loader: () => Promise<Loaded<T>>, deps: unknown[]): LoadState<T> {
  const [s, setS] = useState<{ status: "loading" | "ready" | "error"; data: T | null; meta: AnalyticMeta | null; source: "live" | "demo" | null; why: Fallback | null; error: Error | null }>({
    status: "loading", data: null, meta: null, source: null, why: null, error: null,
  });
  const tick = useRef(0);
  const [n, setN] = useState(0);
  const reload = useCallback(() => setN((x) => x + 1), []);
  useEffect(() => {
    const mine = ++tick.current;
    setS((p) => (p.data ? { ...p, status: "loading" } : { status: "loading", data: null, meta: null, source: null, why: null, error: null }));
    loader().then(
      (r) => { if (mine === tick.current) setS({ status: "ready", data: r.data, meta: r.meta, source: r.source, why: r.why ?? null, error: null }); },
      (e: unknown) => { if (mine === tick.current) setS((p) => ({ ...p, status: "error", error: e instanceof Error ? e : new Error(String(e)) })); },
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, n]);
  return { ...s, reload } as LoadState<T>;
}

/** Track an element's width so SVG charts can choose a layout. Uses a callback ref, so it also works for elements that mount late. */
export function useWidth<T extends HTMLElement>(): [(el: T | null) => void, number] {
  const [el, setEl] = useState<T | null>(null);
  const [w, setW] = useState(0);
  useEffect(() => {
    if (!el) return;
    const ro = new ResizeObserver((entries) => setW(Math.round(entries[0].contentRect.width)));
    ro.observe(el);
    setW(Math.round(el.getBoundingClientRect().width));
    return () => ro.disconnect();
  }, [el]);
  return [setEl, w];
}

export function useTimeout(): (fn: () => void, ms: number) => void {
  const ids = useRef<number[]>([]);
  useEffect(() => () => ids.current.forEach((i) => window.clearTimeout(i)), []);
  return useCallback((fn, ms) => { ids.current.push(window.setTimeout(fn, ms)); }, []);
}

export function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}
