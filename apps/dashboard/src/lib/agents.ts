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
  "data.profile": "Data profile",
  "data.chart": "Chart builder",
  "creative.weekly_summary": "Weekly summary",
};
export const KIND_DOES: Record<string, string> = {
  "programming.commit_analyst": "Reads the sample repo's recent commits and reports habits, such as large commits and missing tests.",
  "programming.test_gap": "Looks for code that changed without a test, in an isolated copy of the repo.",
  "programming.refactor_suggest": "Drafts refactor suggestions as patches. Nothing is applied or pushed without your approval.",
  "data.profile": "Profiles a sample CSV in a sandbox with no network: sizes, gaps and the strongest links.",
  "data.chart": "Builds a chart of a sample CSV in the same sandbox.",
  "creative.weekly_summary": "Drafts a weekly write-up from digests. It cites digest ids only.",
};
export const kindLabel = (k: string): string => KIND_LABEL[k] ?? k;

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

/** The steps of a result, when it has them: each with its label and the check run after it. */
export function stepsOf(result: unknown): { label: string; check: StepCheck | null }[] {
  const steps = result && typeof result === "object" ? (result as { steps?: unknown }).steps : null;
  if (!Array.isArray(steps)) return [];
  return steps.map((s, i) => {
    const o = (s && typeof s === "object" ? s : {}) as Record<string, unknown>;
    const label = [o.step, o.label, o.name, o.action].find((x) => typeof x === "string") as string | undefined;
    const check = o.check === "verified" || o.check === "uncertain" || o.check === "failed" ? o.check : null;
    return { label: label ?? `Step ${i + 1}`, check };
  });
}

/** The result without its steps, so the rest can be shown as plain facts. */
export function resultWithoutSteps(result: unknown): unknown {
  if (result && typeof result === "object" && !Array.isArray(result)) {
    const { steps: _steps, ...rest } = result as Record<string, unknown>;
    void _steps;
    return (rest as { summary?: unknown }).summary && Object.keys(rest).length === 1 ? (rest as { summary: unknown }).summary : rest;
  }
  return result;
}
