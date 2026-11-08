// The status line in the sidebar footer, pure. One honest answer to "is this real?" (docs/KNACK_UX.md section 3, "Live models and example data").
// The dot and the words always travel together: colour is never the only signal. The line says which models Knack is using; the origin badge
// on a screen says where that screen's numbers came from. They are different facts and both stay.
import type { DataMode } from "../../store";

export type StatusKind = "live" | "example" | "some-example" | "down" | "starting" | "connected";
/** solid: a filled dot (good or bad by `tone`). ring: a dashed hollow ring (example or not yet known). */
export interface Status { kind: StatusKind; text: string; dot: "solid" | "ring"; tone: "good" | "bad" | "muted" }

export interface StatusInput {
  /** Whether the engine answered /health. null until the first answer. */
  engineUp: boolean | null;
  /** /health says the engine runs without a model key (example answers by design). null when unknown. */
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
  if (i.mock === true) return { kind: "example", text: "Running with example data", dot: "ring", tone: "muted" };
  if (i.mode === "mixed") return { kind: "some-example", text: "Some example data", dot: "ring", tone: "muted" };
  return { kind: "live", text: "Live models", dot: "solid", tone: "good" };
}

export const wordsOf = (s: string): number => s.trim().split(/\s+/).filter(Boolean).length;
