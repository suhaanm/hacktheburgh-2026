import type { AgentRun, Budget } from "../types";

export interface BudgetBar { key: string; label: string; allowed: number; spent: number; frac: number; over: boolean; text: string }

const UNIT: Record<string, [string, string]> = { steps: ["step", "steps"], seconds: ["s", "s"], tokens: ["token", "tokens"] };

/** One bar per budget the run has: spent against allowed. A bar at 100% or more is flagged. */
export function budgetBars(budget: Budget, spent: Budget): BudgetBar[] {
  return Object.keys(budget)
    .filter((k) => typeof budget[k] === "number" && (budget[k] as number) > 0)
    .map((k) => {
      const allowed = budget[k] as number, used = (spent[k] as number | undefined) ?? 0;
      const [one, many] = UNIT[k] ?? [k, k];
      const unit = k === "seconds" ? " s" : ` ${allowed === 1 ? one : many}`;
      return { key: k, label: k, allowed, spent: used, frac: Math.min(1, used / allowed), over: used >= allowed, text: `${used.toLocaleString("en-GB")} of ${allowed.toLocaleString("en-GB")}${unit}` };
    });
}

export const ACTIVE = new Set(["running", "queued", "paused", "starting"]);
export const isActive = (state: string): boolean => ACTIVE.has(state);
export const runActive = (r: AgentRun): boolean => isActive(r.state) || isActive(r.parent.state) || r.children.some((c) => isActive(c.state));

export type Tone = "go" | "good" | "bad" | "muted";
export function stateTone(state: string): Tone {
  if (state === "running" || state === "starting") return "go";
  if (state === "done" || state === "completed") return "good";
  if (state === "failed" || state === "error") return "bad";
  return "muted";
}

export const KIND_LABEL: Record<string, string> = {
  "programming.commit_analyst": "Commit analyst",
  "programming.test_gap": "Test-gap finder",
  "programming.refactor_suggest": "Refactor suggester",
  "programming.fix_bugs": "Bug fixer (long task)",
  "programming.suite": "Programming suite",
  "data.profile": "Data profile",
  "data.chart": "Chart builder",
  "data.pipeline": "Data pipeline (long task)",
  "data.suite": "Data suite",
  "creative.weekly_summary": "Weekly summary",
};
export const KIND_DOES: Record<string, string> = {
  "programming.commit_analyst": "Reads a repository's recent commits and reports habits, such as large commits and missing tests.",
  "programming.test_gap": "Looks for code that changed without a test, in an isolated copy of the repo.",
  "programming.refactor_suggest": "Drafts refactor suggestions as patches. Nothing is applied or pushed without your approval.",
  "data.profile": "Profiles a CSV file in a sandbox with no network: sizes, gaps and the strongest links.",
  "data.chart": "Builds a chart of a CSV file in the same sandbox.",
  "creative.weekly_summary": "Drafts a weekly write-up from digests. It cites digest ids only.",
};
export const kindLabel = (k: string | null | undefined): string => (typeof k === "string" && k ? KIND_LABEL[k] ?? k.replace(/[._]/g, " ") : "Background run");

/** Run counts by state, for the page header. */
export function countStates(runs: AgentRun[]): { active: number; done: number; failed: number } {
  let active = 0, done = 0, failed = 0;
  for (const r of runs) { if (runActive(r)) active++; else if (r.state === "failed") failed++; else done++; }
  return { active, done, failed };
}

import type { Lease, StepCheck } from "../types";

/** Seconds left on a lease, counting down from when it was fetched. A revoked lease has none. */
export const leaseLeft = (l: Lease, elapsedS: number): number => (l.revoked ? 0 : Math.max(0, Math.round(l.remaining_s - elapsedS)));

export function fmtClock(s: number): string {
  const m = Math.floor(s / 60), r = Math.max(0, Math.round(s % 60));
  return `${m}:${String(r).padStart(2, "0")}`;
}

/** A check is shown with a glyph and a word, never colour alone. */
export const CHECK: Record<StepCheck, { glyph: string; label: string }> = {
  verified: { glyph: "✓", label: "verified" },
  uncertain: { glyph: "?", label: "uncertain" },
  failed: { glyph: "✕", label: "failed" },
};

/** One step as the result lists it: a label, and the check code ran afterwards. */
export interface StepRow { label: string; check: StepCheck | null }

function stepRows(steps: unknown): StepRow[] {
  if (!Array.isArray(steps)) return [];
  return steps.map((s, i) => {
    const o = (s && typeof s === "object" ? s : {}) as Record<string, unknown>;
    const label = [o.step, o.label, o.name, o.action, o.tool].find((x) => typeof x === "string") as string | undefined;
    const check = o.check === "verified" || o.check === "uncertain" || o.check === "failed" ? o.check : null;
    return { label: label ? label.replace(/_/g, " ") : `Step ${i + 1}`, check };
  });
}

/** The steps of a result when it lists them at the top (the contract shape): each with its label and the check run after it. */
export function stepsOf(result: unknown): StepRow[] {
  return stepRows(result && typeof result === "object" ? (result as { steps?: unknown }).steps : null);
}

/** What one helper reported, next to what code found when it checked. A claim of success that the checks do not back is shown as such. */
export interface ChildResult {
  id: string; role: string; status: string; claimed: boolean | null; verified: boolean | null;
  checks: { name: string; ok: boolean; detail: string }[]; steps: StepRow[]; output: unknown; artifacts: { name: string; bytes: number | null }[];
}

/** The per-helper results of a run (the agent service nests them under `result.children`). Empty for the contract's flat shape. */
export function childResults(result: unknown): ChildResult[] {
  const ch = result && typeof result === "object" ? (result as { children?: unknown }).children : null;
  if (!ch || typeof ch !== "object" || Array.isArray(ch)) return [];
  return Object.entries(ch as Record<string, unknown>).map(([id, v]) => {
    const o = (v && typeof v === "object" ? v : {}) as Record<string, unknown>;
    const checks = Array.isArray(o.checks) ? (o.checks as unknown[]).map((c) => { const q = (c && typeof c === "object" ? c : {}) as Record<string, unknown>; return { name: String(q.name ?? "check").replace(/_/g, " "), ok: q.ok === true, detail: typeof q.detail === "string" ? q.detail : "" }; }) : [];
    const artifacts = Array.isArray(o.artifacts) ? (o.artifacts as unknown[]).map((a) => { const q = (a && typeof a === "object" ? a : {}) as Record<string, unknown>; return { name: String(q.name ?? "file"), bytes: typeof q.bytes === "number" ? q.bytes : null }; }) : [];
    return {
      id, role: typeof o.role === "string" ? o.role : id, status: typeof o.status === "string" ? o.status : "unknown",
      claimed: typeof o.claimed_success === "boolean" ? o.claimed_success : null, verified: typeof o.verified === "boolean" ? o.verified : null,
      checks, steps: stepRows(o.steps), output: o.output, artifacts,
    };
  });
}

/** A helper that said it succeeded while code found it did not. This is the number the page must never hide. */
export const falseClaim = (c: Pick<ChildResult, "claimed" | "verified">): boolean => c.claimed === true && c.verified === false;

/** "3 of 3 helpers checked out" for the run's header. Null when the result carries no tally. */
export function verifiedTally(result: unknown): string | null {
  const o = result && typeof result === "object" ? (result as { verified?: unknown; total?: unknown }) : null;
  if (!o || typeof o.verified !== "number" || typeof o.total !== "number") return null;
  return `${o.verified} of ${o.total} ${o.total === 1 ? "helper" : "helpers"} checked out when code verified the result`;
}

/** Why a lease ended, in words. */
export const STOP_REASON: Record<string, string> = { run_finished: "the run finished", expired: "it ran out of time", step_cap: "it used its steps", revoked: "you ended it", parent_revoked: "its parent was ended" };
export const stopReason = (r: string | undefined): string => (r ? STOP_REASON[r] ?? r.replace(/_/g, " ") : "");

/** The result without its steps (and without the per-helper block, which is shown separately), so the rest can be shown as plain facts. */
export function resultWithoutSteps(result: unknown): unknown {
  if (result && typeof result === "object" && !Array.isArray(result)) {
    const { steps: _steps, children: _children, ...rest } = result as Record<string, unknown>;
    void _steps; void _children;
    return (rest as { summary?: unknown }).summary && Object.keys(rest).length === 1 ? (rest as { summary: unknown }).summary : rest;
  }
  return result;
}
