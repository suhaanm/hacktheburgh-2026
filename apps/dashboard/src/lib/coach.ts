// The coach answers (GET /coach/state, GET /coach/next) are whatever the engine sent: a missing field, a null, a number where a string was promised, a list of
// 20 actions or six. The Today screen and the Home row read them through these functions, so a surprising answer becomes a calm screen, never a thrown error.
// Pure: no React, no window.
import type { CoachDecision, CoachState } from "../types";

export type Level = CoachState["level"];
export type Chip = CoachState["chip"];
const LEVELS: readonly Level[] = ["L1", "L2", "L3", "L4"];
const CHIPS: readonly Chip[] = ["full", "small", "dot", "gone"];
const ACTIONS: readonly CoachDecision["action"][] = ["silent", "nudge", "annotate", "takeover_offer"];

/** The most step marks one task draws: a total past this is a broken answer, and one mark per step would fill the screen. */
export const MAX_STEPS = 40;

const isObj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
const str = (v: unknown): string => (typeof v === "string" ? v : "");
const strs = (v: unknown): string[] => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []);
const oneOf = <T extends string>(v: unknown, all: readonly T[], fallback: T): T => (typeof v === "string" && (all as readonly string[]).includes(v) ? (v as T) : fallback);
const whole = (v: unknown): number | null => { const n = typeof v === "number" ? v : typeof v === "string" && v.trim() !== "" ? Number(v) : NaN; return Number.isInteger(n) ? n : null; };

/** Action name to a 0 to 1 number; anything that is not a finite number is left out (a row with no number would read "NaN"). */
export function readMastery(v: unknown): Record<string, number> {
  const out: Record<string, number> = {};
  if (!isObj(v)) return out;
  for (const [k, m] of Object.entries(v)) if (typeof m === "number" && Number.isFinite(m)) out[k] = Math.min(1, Math.max(0, m));
  return out;
}

export interface CoachView {
  /** The engine's id for the worker, when the state names one (a learner trajectory does). */
  person: string | null;
  task: { id: string; name: string; step: number | null; total: number };
  /** True when the state names a task (a name); the Today screen has nothing to draw as the task without one. */
  hasTask: boolean;
  /** The engine's own word on whether a task window is open now; null when it did not say (an older engine). */
  active: boolean | null;
  level: Level;
  chip: Chip;
  message: string;
  why: string;
  mastery: Record<string, number>;
}

/** The coach state, made safe: every field has the type the screen needs, a step count past MAX_STEPS or below 1 is "unknown" (0), a step outside 1..total is cut to it. */
export function readCoachState(raw: unknown): CoachView {
  const o = isObj(raw) ? raw : {};
  const t = isObj(o.task) ? o.task : {};
  const total0 = whole(t.steps_total);
  const total = total0 !== null && total0 >= 1 ? Math.min(total0, MAX_STEPS) : 0;
  const step0 = whole(t.step);
  const step = step0 !== null && step0 >= 1 ? (total > 0 ? Math.min(step0, total) : step0) : null;
  const name = str(t.name).replace(/\s+/g, " ").trim();
  return {
    person: typeof o.person === "string" && o.person !== "" ? o.person : null,
    task: { id: str(t.id), name, step, total },
    hasTask: name !== "",
    active: typeof o.active === "boolean" ? o.active : null,
    level: oneOf(o.level, LEVELS, "L4"),
    chip: oneOf(o.chip, CHIPS, "gone"),
    message: str(o.message),
    why: str(o.why),
    mastery: readMastery(o.mastery),
  };
}

/** What the screen draws from a coach decision: the contract's fields, each safe to read. */
export interface DecisionView extends Omit<CoachDecision, "step" | "candidate" | "target" | "missed" | "gate"> {
  /** The engine names the step it is on by id, not by number: the number on the screen comes from the coach state. */
  step: number | null;
  missed: unknown[];
  target: CoachDecision["target"];
  gate: { consecutive?: number; reason?: string };
  candidate: { message: string; why: string } | null;
}

/** A decision, made safe. `null` (no answer yet) gives the decision the coach state implies: the state's own message, or silence. */
export function readDecision(raw: unknown, state: CoachView): DecisionView {
  if (!isObj(raw)) {
    const speaks = state.message.trim() !== "" && state.active !== false;
    return {
      action: speaks ? "nudge" : "silent", message: speaks ? state.message : "", why: state.why, target: null, missed: [], confidence: 0, level: state.level, chip: state.chip,
      decision_id: null, task_id: state.task.id || null, step: state.task.step, trigger: null, reason_codes: state.active === false ? ["no_active_task"] : [], gate: {},
      p_stuck: null, p_source: null, mastery: state.mastery, candidate: null,
    };
  }
  const tg = isObj(raw.target) ? raw.target : null;
  const target = tg ? { zone: str(tg.zone) || undefined, label_hint: str(tg.label_hint) || undefined, role_hint: str(tg.role_hint) || undefined, site: str(tg.site) || undefined } : null;
  const g = isObj(raw.gate) ? raw.gate : {};
  const c = isObj(raw.candidate) ? raw.candidate : null;
  const cand = c && str(c.message).trim() !== "" ? { message: str(c.message), why: str(c.why) } : null;
  return {
    action: oneOf(raw.action, ACTIONS, "silent"),
    message: str(raw.message),
    why: str(raw.why),
    target,
    missed: Array.isArray(raw.missed) ? raw.missed : [],
    confidence: typeof raw.confidence === "number" && Number.isFinite(raw.confidence) ? raw.confidence : 0,
    level: oneOf(raw.level, LEVELS, state.level),
    chip: oneOf(raw.chip, CHIPS, state.chip),
    decision_id: typeof raw.decision_id === "string" && raw.decision_id !== "" ? raw.decision_id : null,
    task_id: typeof raw.task_id === "string" ? raw.task_id : null,
    step: null,
    trigger: typeof raw.trigger === "string" && raw.trigger !== "" ? raw.trigger : null,
    reason_codes: strs(raw.reason_codes),
    gate: { consecutive: typeof g.consecutive === "number" && Number.isFinite(g.consecutive) ? g.consecutive : undefined, reason: typeof g.reason === "string" ? g.reason : undefined },
    p_stuck: typeof raw.p_stuck === "number" && Number.isFinite(raw.p_stuck) ? raw.p_stuck : null,
    p_source: typeof raw.p_source === "string" ? raw.p_source : null,
    candidate: cand,
    mastery: readMastery(raw.mastery),
  };
}

/** Reason codes that mean no task window is open: the coach has nothing to coach on. */
const IDLE_REASONS = ["no_active_task", "no_events"];

/**
 * Is there a step to coach on? A live decision decides when there is one (its reason codes), else the state's own `active` flag; with neither,
 * a named task with a step counts (an engine that does not send the flag). A task with no name or no step is not a task.
 */
export function isCoaching(state: CoachView, decision: Pick<DecisionView, "reason_codes"> | null): boolean {
  if (!state.hasTask || state.task.step === null) return false;
  if (decision && decision.reason_codes.some((c) => IDLE_REASONS.includes(c))) return false;
  if (state.active === false) return false;
  return true;
}

/** "Step 3 of 5", "Step 3" when the total is unknown, or null when there is no step. */
export function stepLabel(step: number | null, total: number): string | null {
  if (step === null) return null;
  return total > 0 ? `Step ${Math.min(step, total)} of ${total}` : `Step ${step}`;
}

/** The task name for a row of one line: cut at its first comma, colon or bracket ("Entitlement check, household H-9"), at most nine words, with an ellipsis when cut. */
export function shortTaskName(name: string): string {
  const head = name.split(/[,:;(]/)[0].replace(/\s+/g, " ").trim();
  const words = head.split(" ");
  return words.length > 9 ? `${words.slice(0, 9).join(" ")}…` : head;
}
