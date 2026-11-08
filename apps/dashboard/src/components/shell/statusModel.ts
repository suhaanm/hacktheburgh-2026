// The status line in the sidebar footer, pure. One honest answer about the connection and the models (docs/KNACK_UX.md section 3). The dot and the words
// always travel together: colour is never the only signal. The line says whether Knack can reach its engine and whether live models are on; it says nothing
// about what kind of data a screen holds (owner, 8 Nov 2026).
import type { DataMode } from "../../store";

export type StatusKind = "live" | "down" | "starting" | "connected";
/** solid: a filled dot (good or bad by `tone`). ring: a dashed hollow ring (not yet known, or no live model). */
export interface Status { kind: StatusKind; text: string; dot: "solid" | "ring"; tone: "good" | "bad" | "muted" }

export interface StatusInput {
  /** Whether the engine answered /health. null until the first answer. */
  engineUp: boolean | null;
  /** /health says the engine runs without a model key. null when unknown. */
  mock: boolean | null | undefined;
  /** How the sources on the current screen answered. */
  mode: DataMode;
  /** Milliseconds since the app started waiting for the first answer. After 30 s a silent engine is reported as unreachable. */
  waitedMs?: number;
}

export const STARTING_GIVE_UP_MS = 30_000;

export function statusFor(i: StatusInput): Status {
  if (i.engineUp === false || (i.engineUp === null && (i.waitedMs ?? 0) >= STARTING_GIVE_UP_MS)) {
    return { kind: "down", text: "Cannot reach the engine", dot: "solid", tone: "bad" };
  }
  if (i.engineUp === null) return { kind: "starting", text: "Starting", dot: "ring", tone: "muted" };
  if (i.mock === null || i.mock === undefined) return { kind: "connected", text: "Connected", dot: "ring", tone: "muted" };
  if (i.mock === true || i.mode === "mixed") return { kind: "connected", text: "Connected", dot: "ring", tone: "muted" };
  return { kind: "live", text: "Live models", dot: "solid", tone: "good" };
}

export const wordsOf = (s: string): number => s.trim().split(/\s+/).filter(Boolean).length;
