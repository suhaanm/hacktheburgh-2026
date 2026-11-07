import { useSyncExternalStore } from "react";

/** Tiny shared store: where data came from, the kill state, and the pending-queue badge. */
export interface AppState {
  live: number;
  demo: number;
  mock: boolean | null;
  killed: boolean;
  killedAt: string | null;
  killError: string | null;
  pendingQueue: number;
}

let state: AppState = { live: 0, demo: 0, mock: null, killed: false, killedAt: null, killError: null, pendingQueue: 0 };
const listeners = new Set<() => void>();

export function setState(patch: Partial<AppState>): void {
  state = { ...state, ...patch };
  listeners.forEach((l) => l());
}

export function getState(): AppState {
  return state;
}

export function noteSource(source: "live" | "demo"): void {
  setState(source === "live" ? { live: state.live + 1 } : { demo: state.demo + 1 });
}

export function resetSources(): void {
  setState({ live: 0, demo: 0 });
}

export function useAppState(): AppState {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => state,
  );
}

export type DataMode = "live" | "mixed" | "demo" | "unknown";
export function dataMode(s: AppState): DataMode {
  if (s.live && s.demo) return "mixed";
  if (s.live) return "live";
  if (s.demo) return "demo";
  return "unknown";
}
