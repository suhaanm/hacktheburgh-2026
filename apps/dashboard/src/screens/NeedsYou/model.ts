// Needs you: ONE list for everything that waits on the worker (docs/knack-ux/02-needs-you.md). Pure: no network, no React.
// The model proposes, code decides: the order is a fixed table (safety, then time-sensitive, then the rest, newest first inside a class).
import type { AgentRun, BriefingCard, QueueItem, Routine } from "../../types";

/** 0 safety, 1 time-sensitive (a decision a job waits on), 2 can wait. docs/ATTENTION_DESIGN.md section 1. */
export type NeedsClass = 0 | 1 | 2;

export type NeedsItem =
  | { key: string; kind: "approval"; cls: NeedsClass; when: string | null; queue: QueueItem }
  | { key: string; kind: "proposal"; cls: NeedsClass; when: string | null; routine: Routine }
  | { key: string; kind: "prepared"; cls: NeedsClass; when: string | null; card: BriefingCard }
  | { key: string; kind: "paused"; cls: NeedsClass; when: string | null; run: AgentRun };

/** At most this many rows show by default, then "Show all N" (design README rule 4). */
export const DEFAULT_ROWS = 7;

/** An approval's class: a pause for safety and an irreversible step are safety; an outward step is a decision a job waits on; the rest can wait. */
export function approvalClass(q: Pick<QueueItem, "kind" | "risk_class">): NeedsClass {
  if (q.kind === "injection_pause" || q.risk_class === "irreversible") return 0;
  if (q.kind === "outward_step" || q.risk_class === "outward") return 1;
  return 2;
}

const PAUSED = new Set(["paused", "needs_human", "blocked"]);
export const isPausedRun = (r: AgentRun): boolean => PAUSED.has(r.state) || PAUSED.has(r.parent.state);

const ms = (iso: string | null): number => { const t = iso ? Date.parse(iso) : NaN; return Number.isNaN(t) ? -Infinity : t; };

/** Everything that waits on the worker, in the order it is shown. A source that has not loaded yet is simply absent. */
export function buildItems(src: { queue?: QueueItem[] | null; routines?: Routine[] | null; cards?: BriefingCard[] | null; cardsAt?: string | null; runs?: AgentRun[] | null }): NeedsItem[] {
  const out: NeedsItem[] = [];
  for (const q of src.queue ?? []) {
    if (q.status !== "pending") continue;
    out.push({ key: `q:${q.id}`, kind: "approval", cls: approvalClass(q), when: q.created_at, queue: q });
  }
  for (const r of src.routines ?? []) {
    if (r.status !== "proposed") continue;
    out.push({ key: `r:${r.id}`, kind: "proposal", cls: 2, when: null, routine: r });
  }
  for (const c of src.cards ?? []) {
    if (c.status !== "ready") continue;
    out.push({ key: `b:${c.id}`, kind: "prepared", cls: 2, when: src.cardsAt ?? null, card: c });
  }
  for (const run of src.runs ?? []) {
    if (!isPausedRun(run)) continue;
    out.push({ key: `a:${run.run_id}`, kind: "paused", cls: 1, when: run.started, run });
  }
  return out
    .map((it, i) => ({ it, i }))
    .sort((a, b) => a.it.cls - b.it.cls || ms(b.it.when) - ms(a.it.when) || a.i - b.i)
    .map((x) => x.it);
}

/** The one number the sidebar badge, the menu bar and the Dock all show. */
export const needsCount = (items: NeedsItem[]): number => items.length;

/** The consequence of a step, printed whole as plain text. Never a pill, never behind a Hint. Null for a normal step. */
export function consequence(risk: "irreversible" | "outward" | "normal" | string): string | null {
  if (risk === "irreversible") return "Cannot be undone.";
  if (risk === "outward") return "Reaches outside.";
  return null;
}

/** The button labels of an approval, by kind. The irreversible-step label stays ("Approve and submit"). */
export function approvalLabels(kind: QueueItem["kind"]): { yes: string; no: string } {
  switch (kind) {
    case "irreversible_step": return { yes: "Approve and submit", no: "Reject" };
    case "outward_step": return { yes: "Approve and send", no: "Reject" };
    case "injection_pause": return { yes: "Resume the run", no: "Cancel the run" };
    case "shadow_mismatch": return { yes: "Accept its answer", no: "Keep mine" };
    default: return { yes: "Approve", no: "Reject" };
  }
}

/**
 * The engine's own sentences still carry words the worker never sees: "shadow run", a rung and its code (A0 to A3) and the old name. This is the
 * one place they become the worker's words, for anything an engine sentence prints on Needs you and Routines (docs/KNACK_UX.md section 5).
 */
export function plainWords(text: string): string {
  const keep = (from: string, to: string) => (from.charAt(0) === from.charAt(0).toUpperCase() ? to.charAt(0).toUpperCase() + to.slice(1) : to);
  return text
    .replace(/\bshadow (run|copy|runs|copies)\b/gi, (m, w: string) => keep(m, `practice ${w.toLowerCase()}`))
    .replace(/\bshadow\b/gi, (m) => keep(m, "practice"))
    .replace(/\bUnderstudy\b/g, "Knack")
    .replace(/\brung A0\b/gi, "observing").replace(/\brung A1\b/gi, "watching").replace(/\brung A2\b/gi, "asking first").replace(/\brung A3\b/gi, "running on its own")
    .replace(/\bA0\b/g, "observing").replace(/\bA1\b/g, "watching").replace(/\bA2\b/g, "asking first").replace(/\bA3\b/g, "running on its own")
    .replace(/\brungs\b/gi, (m) => keep(m, "steps")).replace(/\brung\b/gi, (m) => keep(m, "step"));
}

const WORDS = (s: string): number => s.trim().split(/\s+/).filter(Boolean).length;
/** Split a sentence run into what shows (at most `max` words, whole sentences) and the rest, which waits in the evidence. */
export function leadAndRest(text: string, max = 24): { lead: string; rest: string } {
  const sentences = plainWords(text).split(/(?<=[.!?])\s+/).filter(Boolean);
  let lead = "";
  let n = 0;
  let i = 0;
  for (; i < sentences.length; i++) {
    const w = WORDS(sentences[i]);
    if (i > 0 && n + w > max) break;
    lead += (lead ? " " : "") + sentences[i];
    n += w;
  }
  return { lead, rest: sentences.slice(i).join(" ") };
}

/** "Seen about 58 times in 3 weeks." from the engine's own "about 58 times in 3 weeks". */
export function seenLine(howOften: string): string {
  const t = howOften.trim().replace(/\.$/, "");
  return /^seen\b/i.test(t) ? `${t}.` : `Seen ${t.charAt(0).toLowerCase()}${t.slice(1)}.`;
}

const trim1 = (n: number): string => n.toFixed(1).replace(/\.0$/, "");
/** "Could save 3.1 to 5.2 hours." One range, one quantity. */
export function saveLine(r: Pick<Routine, "value">): string {
  const [lo, hi] = r.value.hours_saved;
  return `Could save ${trim1(lo)} to ${trim1(hi)} hours.`;
}

/** What is behind the "i" beside the hours: the interval and the money, never the only copy of a fact. */
export function saveHint(r: Pick<Routine, "value">): string {
  const v = r.value;
  const wk = v.horizon_weeks ? ` over ${v.horizon_weeks} weeks` : "";
  return `95% interval${wk}. About £${v.net_gbp[0]} to £${v.net_gbp[1]} net of set-up.`;
}

/** "Touches GovCalc and 3 more." The whole list is one click away. */
export function touchesLead(touches: string[], show = 2): { lead: string; more: number } {
  if (touches.length <= show + 1) return { lead: touches.join(", "), more: 0 };
  const head = touches.slice(0, show);
  return { lead: head.join(", "), more: touches.length - show };
}

/** "It will never submit the case note, send anything to a claimant or open sites you have not used in this routine." Printed whole. */
export function neverLine(never: string[]): string {
  if (never.length === 0) return "";
  const low = never.map((n) => n.charAt(0).toLowerCase() + n.slice(1));
  const body = low.length === 1 ? low[0] : `${low.slice(0, -1).join(", ")} or ${low[low.length - 1]}`;
  return `It will never ${body.replace(/\.$/, "")}.`;
}

/** The overnight report as one line: "Since you were away: 1 run finished, 0 failed." */
export function awayLine(rep: { ran: unknown[]; failed: unknown[]; queued?: unknown[]; yielded?: unknown[] } | null): string | null {
  if (!rep) return null;
  const n = rep.ran.length, f = rep.failed.length;
  if (n === 0 && f === 0) return null;
  return `Since you were away: ${n} ${n === 1 ? "run" : "runs"} finished, ${f} failed.`;
}

/** Counts of a list: how many show, how many are folded. */
export function visible<T>(rows: T[], showAll: boolean, limit = DEFAULT_ROWS): T[] {
  return showAll || rows.length <= limit ? rows : rows.slice(0, limit);
}

/** Plain words for what a pressed card made. Its row is gone from the list, so this line is where the worker sees what happened. */
export function madeLine(f: { queue_id?: string; run_id?: string }): string {
  if (f.queue_id && f.run_id) return "Created an item here for your approval and started a background run.";
  if (f.queue_id) return "Created an item here for your approval. Nothing runs until you approve it.";
  if (f.run_id) return "Started a background run that only reads. Stop it any time in Background runs.";
  return "Done. The engine did not say what it created.";
}

