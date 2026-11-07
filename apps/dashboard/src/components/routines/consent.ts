// Consent wording and rules shared by Needs you (a routine proposal) and Routines (managing one). Pure.
// A consent says what will happen and gives "Not now" and "Never" the weight of "Yes" (docs/KNACK_UX.md section 5, Voice).
import type { Rung, Routine } from "../../types";
import { cleanRunsNeeded } from "../../lib/wilson";

/** What each choice does, printed once beside the choices. "Never" and "Not now" are as plain as "Watch first". */
export const WATCH_TEXT = "Watch first: it practises beside you. Nothing is saved or sent.";
export const APPROVAL_TEXT = "Run with my approval: it works in the background and asks before anything outward.";
/** The consent for running while the worker is away, printed whole beside its button. */
export const AWAY_TEXT = "It runs only in away windows, never in quiet hours, and stops within a second of you touching the keyboard.";

export const IRREVERSIBLE_MODEL = "This routine is driven by a model, which can misread a page. An irreversible step could go wrong with nobody watching.";
export const IRREVERSIBLE_SCRIPT = "This is a recorded script. It repeats exactly what you did, so an irreversible step cannot be taken back.";

/** The three steps of how far a routine is trusted, in the worker's words (never A0 to A3). */
export type Cap = "watching" | "asks" | "own";
export const CAP_LABEL: Record<Cap, string> = { watching: "Watching", asks: "Asks first", own: "Runs on its own" };
export const CAP_MODE: Record<Cap, "shadow" | "approval" | "unattended"> = { watching: "shadow", asks: "approval", own: "unattended" };

/** The step the worker chose: the consent mode, in words. Away runs ask before anything outward too, so they read as the top step. */
export function capOf(status: Routine["status"]): Cap | null {
  if (status === "shadow") return "watching";
  if (status === "approval") return "asks";
  if (status === "unattended") return "own";
  return null;
}

const RUNG_STEP: Record<Rung, number> = { A0: 0, A1: 1, A2: 2, A3: 3 };
const CAP_STEP: Record<Cap, number> = { watching: 1, asks: 2, own: 3 };

/** Whether a step up is offered: only when the record earned it (or the worker already chose it). A step down is always offered. */
export function stepState(r: Pick<Routine, "rung" | "status" | "shadow">, step: Cap): { enabled: boolean; need: string | null } {
  const here = capOf(r.status);
  const chosen = here ? CAP_STEP[here] : 0;
  if (CAP_STEP[step] <= Math.max(chosen, 1)) return { enabled: true, need: null };
  if (RUNG_STEP[r.rung] >= CAP_STEP[step]) return { enabled: true, need: null };
  return { enabled: false, need: needFor(r, step) };
}

/** "Needs 8 more matching practice runs." Printed, not in a Hint. */
export function needFor(r: Pick<Routine, "shadow">, step: Cap): string {
  const { runs, matches } = r.shadow;
  const bound = step === "asks" ? 0.8 : 0.95;
  const minRuns = step === "asks" ? 20 : 75;
  const clean = cleanRunsNeeded(matches, runs, bound);
  const more = clean == null ? null : Math.max(clean, Math.max(0, minRuns - runs));
  if (more == null) return "Not within reach with this record.";
  if (more === 0) return "The record is ready for this step.";
  return `Needs ${more} more matching practice ${more === 1 ? "run" : "runs"}.`;
}

/** The state of a routine in one sentence of its own words. */
export function stateLine(r: Pick<Routine, "rung" | "status" | "shadow">): string {
  const { runs, matches } = r.shadow;
  if (r.status === "unattended") return r.rung === "A3" ? "Runs, then tells you." : "Runs while you are away. Asks before it submits or sends.";
  if (r.rung === "A2" || r.rung === "A3") return "Asks before it submits or sends.";
  return runs > 0 ? `Watching: ${matches} of ${runs} practice runs match.` : "Watching: no practice runs yet.";
}

/** The label at the right edge of a row: how far the worker trusts it. */
export function trustWord(r: Pick<Routine, "status">): string {
  const c = capOf(r.status);
  return c === "own" ? "Runs while away" : c ? CAP_LABEL[c] : "";
}
