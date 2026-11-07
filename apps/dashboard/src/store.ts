import { useSyncExternalStore } from "react";
import type { ExtFlags } from "./lib/ext";

/** Tiny shared store: where data came from, the kill state, and the pending-queue badge. */
export interface AppState {
  live: number;
  demo: number;
  mock: boolean | null;
  killed: boolean;
  killedAt: string | null;
  killError: string | null;
  pendingQueue: number;
  /** The role the engine knows the worker by, once onboarding has run. */
  role: string | null;
  /** Which REQ-2 layers are on. `extReady` is false until /health has answered. */
  ext: ExtFlags;
  extReady: boolean;
  /** The engine's id for the worker once onboarding has run; null before. */
  person: string | null;
  /** Whether the agent service (port 7710) answered its health check. null until asked. */
  agentUp: boolean | null;
  /** Whether the engine (port 7700) answered /health. null until asked; the status line and the Home states read it. */
  engineUp: boolean | null;
}

let state: AppState = { live: 0, demo: 0, mock: null, killed: false, killedAt: null, killError: null, pendingQueue: 0, role: null, ext: {}, extReady: false, person: null, agentUp: null, engineUp: null };
const listeners = new Set<() => void>();

export function setState(patch: Partial<AppState>): void {
  state = { ...state, ...patch };
  listeners.forEach((l) => l());
}

export function getState(): AppState {
  return state;
}

/** Resolves once /health has said which layers are on (or after `maxMs`, so a screen never waits for ever). */
export function whenExtReady(maxMs = 2500): Promise<void> {
  if (state.extReady) return Promise.resolve();
  return new Promise((resolve) => {
    const done = () => { listeners.delete(check); window.clearTimeout(timer); resolve(); };
    const check = () => { if (state.extReady) done(); };
    const timer = window.setTimeout(done, maxMs);
    listeners.add(check);
  });
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
