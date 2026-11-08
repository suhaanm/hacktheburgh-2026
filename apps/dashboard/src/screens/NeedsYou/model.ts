// Needs you: ONE list for everything that waits on the worker (docs/knack-ux/02-needs-you.md). Pure: no network, no React.
// The model proposes, code decides: the order is a fixed table (safety, then time-sensitive, then the rest, newest first inside a class).
import { arr, clip, num, uniqueBy } from "../../lib/safeText";
import { isGhostRow, isGhostRun } from "../../lib/tasks";
import type { AgentRun, BriefingCard, QueueItem, Routine, TaskRow } from "../../types";

/** 0 safety, 1 time-sensitive (a decision a job waits on), 2 can wait. docs/ATTENTION_DESIGN.md section 1. */
export type NeedsClass = 0 | 1 | 2;

export type NeedsItem =
  | { key: string; kind: "approval"; cls: NeedsClass; when: string | null; queue: QueueItem }
  | { key: string; kind: "proposal"; cls: NeedsClass; when: string | null; routine: Routine; /** A prepared action about the same routine: its words wait in the proposal's Details, it is not a second row. */ also?: BriefingCard }
  | { key: string; kind: "prepared"; cls: NeedsClass; when: string | null; card: BriefingCard }
  | { key: string; kind: "paused"; cls: NeedsClass; when: string | null; run: AgentRun }
  | { key: string; kind: "task"; cls: NeedsClass; when: string | null; task: TaskRow };

/** At most this many rows show by default, then "Show all N" (design README rule 4: at most 7). Routines lists show seven. */
export const DEFAULT_ROWS = 7;
/**
 * Needs you shows three rows by default: three decisions, with their buttons, fit a 735 px window (docs/knack-ux/02-needs-you.md). Safety and
 * blocking items are never folded: every row of class 0 or 1 shows, however many there are. The sidebar badge counts the same list.
 */
export const NEEDS_ROWS = 3;
/** The most rows drawn at once, and the size of each further page: a list of hundreds is paged, never drawn whole. */
export const MAX_ROWS = 60;
export const PAGE_ROWS = 50;

/** An approval's class: a pause for safety and an irreversible step are safety; an outward step is a decision a job waits on; the rest can wait. */
export function approvalClass(q: Pick<QueueItem, "kind" | "risk_class">): NeedsClass {
  if (q.kind === "injection_pause" || q.risk_class === "irreversible") return 0;
  if (q.kind === "outward_step" || q.risk_class === "outward") return 1;
  return 2;
}

const PAUSED = new Set(["paused", "needs_human", "blocked"]);
/** True once every source has answered at least once (data, or a failure): a list built before that is partial. A reload keeps the old data, so it stays true. */
export const firstLoadDone = (sources: ReadonlyArray<{ data: unknown; status: string }>): boolean => sources.every((x) => x.data !== null && x.data !== undefined ? true : x.status !== "loading");

/** A field key from a run as a person reads it: `case_ref` is "Case ref". */
export const fieldName = (k: string): string => { const t = String(k ?? "").replace(/[_-]+/g, " ").trim(); return t ? t.charAt(0).toUpperCase() + t.slice(1) : String(k ?? ""); };
export const isPausedRun = (r: AgentRun): boolean => PAUSED.has(r?.state) || PAUSED.has(r?.parent?.state);

const ms = (iso: string | null): number => { const t = iso ? Date.parse(iso) : NaN; return Number.isNaN(t) ? -Infinity : t; };

/**
 * Everything that waits on the worker, in the order it is shown. A source that has not loaded yet is simply absent. An entry that is not an object is
 * skipped, one without an id is keyed by its place in the list, and an id that comes twice is one item (the first), so a list never has two rows
 * with the same key.
 */
export function buildItems(src: { queue?: QueueItem[] | null; routines?: Routine[] | null; cards?: BriefingCard[] | null; cardsAt?: string | null; runs?: AgentRun[] | null; tasks?: TaskRow[] | null; /** The clock, for the ghost test (a test fixes it). */ now?: number }): NeedsItem[] {
  const now = src.now ?? Date.now();
  const out: NeedsItem[] = [];
  const idOf = <T extends object>(field: string) => (row: T, i: number): string => { const v = (row as Record<string, unknown>)[field]; return typeof v === "string" && v ? v : typeof v === "number" ? String(v) : `#${i}`; };
  for (const q of uniqueBy<QueueItem>(src.queue, idOf("id"))) {
    if (q.status !== "pending") continue;
    out.push({ key: `q:${idOf("id")(q, out.length)}`, kind: "approval", cls: approvalClass(q), when: typeof q.created_at === "string" ? q.created_at : null, queue: q });
  }
  for (const r of uniqueBy<Routine>(src.routines, idOf("id"))) {
    if (r.status !== "proposed") continue;
    out.push({ key: `r:${idOf("id")(r, out.length)}`, kind: "proposal", cls: 2, when: null, routine: r });
  }
  for (const c of uniqueBy<BriefingCard>(src.cards, idOf("id"))) {
    if (c.status !== "ready") continue;
    // The same routine as a proposal ("Automate: X" beside "X"): one row, the proposal's; the prepared action's words go into its Details.
    const twin = out.find((it) => it.kind === "proposal" && !it.also && sameRoutine(c, it.routine));
    if (twin && twin.kind === "proposal") { twin.also = c; continue; }
    out.push({ key: `b:${idOf("id")(c, out.length)}`, kind: "prepared", cls: 2, when: src.cardsAt ?? null, card: c });
  }
  for (const run of uniqueBy<AgentRun>(src.runs, idOf("run_id"))) {
    if (!isPausedRun(run) || isGhostRun(run, now)) continue;      // a record a dead process left 'paused' is not waiting for anyone
    out.push({ key: `a:${idOf("run_id")(run, out.length)}`, kind: "paused", cls: 1, when: typeof run.started === "string" ? run.started : null, run });
  }
  // A task that waits for the worker: a consent card, or a question. The card's words are in the row; nothing here decides for the worker.
  for (const t of uniqueBy<TaskRow>(src.tasks, idOf("task_id"))) {
    const waits = (t.state === "waiting_consent" && !!t.needs_consent) || (!!t.question && typeof t.question.text === "string" && t.state !== "done" && t.state !== "stopped" && t.state !== "failed");
    if (!waits || isGhostRow(t, now)) continue;
    out.push({ key: `t:${idOf("task_id")(t, out.length)}`, kind: "task", cls: 1, when: typeof t.started === "string" ? t.started : null, task: t });
  }
  // A key can still repeat when two ids were missing in different places: make every key unique, keeping order.
  const seen = new Map<string, number>();
  for (const it of out) { const n = (seen.get(it.key) ?? 0) + 1; seen.set(it.key, n); if (n > 1) it.key = `${it.key}~${n}`; }
  return out
    .map((it, i) => ({ it, i }))
    .sort((a, b) => a.it.cls - b.it.cls || ms(b.it.when) - ms(a.it.when) || a.i - b.i)
    .map((x) => x.it);
}

const normTitle = (t: unknown): string => plainWords(typeof t === "string" ? t : "").toLowerCase().replace(/^automate:\s*/, "").replace(/\s+/g, " ").trim();
const FILLER = new Set(["let", "knack", "automate", "the", "a", "an", "into", "to", "and", "for", "of", "it", "me", "my", "your", "you", "with", "on", "in"]);
/** The words of a title that carry its meaning: no filler, plural endings taken off ('households' and 'household' are one word). */
const meaningWords = (t: unknown): Set<string> => new Set(normTitle(t).replace(/[^a-z0-9 ]+/g, " ").split(" ").filter((w) => w && !FILLER.has(w)).map((w) => (w.length > 3 && w.endsWith("s") ? w.slice(0, -1) : w)));
/**
 * A prepared action and a routine proposal are about the same routine when their titles match once the 'Automate:' lead-in is taken off, or, for an
 * 'automate' card, when they say the same thing in other words ('Let Knack enter households into the three calculators' and 'Enter the household into three
 * calculators': the same four meaning words). Anything else stays its own row.
 */
export function sameRoutine(card: Pick<BriefingCard, "title"> & { kind?: string }, routine: Pick<Routine, "title">): boolean {
  const a = normTitle(card?.title);
  if (a === "") return false;
  if (a === normTitle(routine?.title)) return true;
  if (card?.kind !== "automate" && !/^automate:/i.test(String(card?.title ?? ""))) return false;
  const x = meaningWords(card?.title), y = meaningWords(routine?.title);
  if (x.size < 3 || y.size < 3) return false;
  let both = 0;
  for (const w of x) if (y.has(w)) both++;
  return both / (x.size + y.size - both) >= 0.75;
}

/** A routine's name for a worker: an id like 'benefits-workflow' becomes 'Benefits workflow'; a name with spaces is left as it is. */
export function routineName(v: unknown): string {
  const s = typeof v === "string" ? v.trim() : "";
  if (!s) return "A routine";
  const t = /\s/.test(s) || !/[-_]/.test(s) ? s : s.replace(/[-_]+/g, " ");
  return t.charAt(0).toUpperCase() + t.slice(1);
}

/** A length of time in the words a person says: 'under a minute', '40 minutes', '8 hours', '3 days'. Anything that is not a sensible number is no duration (null). */
export function plainDuration(minutes: unknown): string | null {
  if (typeof minutes !== "number" || !Number.isFinite(minutes) || minutes < 0) return null;
  if (minutes < 1) return "under a minute";
  if (minutes < 90) { const m = Math.round(minutes); return `${m} ${m === 1 ? "minute" : "minutes"}`; }
  if (minutes < 48 * 60) { const h = Math.round(minutes / 60); return `${h} ${h === 1 ? "hour" : "hours"}`; }
  const d = Math.round(minutes / 1440);
  return `${d} days`;
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
export function plainWords(input: string | null | undefined): string {
  const text = typeof input === "string" ? input : "";
  const keep = (from: string, to: string) => (from.charAt(0) === from.charAt(0).toUpperCase() ? to.charAt(0).toUpperCase() + to.slice(1) : to);
  return text
    .replace(/\bshadow (run|copy|runs|copies)\b/gi, (m, w: string) => keep(m, `practice ${w.toLowerCase()}`))
    .replace(/\bshadow\b/gi, (m) => keep(m, "practice"))
    .replace(/\bUnderstudy\b/g, "Knack")
    .replace(/\bdemo mode\b/gi, (x) => keep(x, "example data")).replace(/\bdemo\b/gi, (x) => keep(x, "example"))
    .replace(/\brung A0\b/gi, "observing").replace(/\brung A1\b/gi, "watching").replace(/\brung A2\b/gi, "asking first").replace(/\brung A3\b/gi, "running on its own")
    .replace(/\bA0\b/g, "observing").replace(/\bA1\b/g, "watching").replace(/\bA2\b/g, "asking first").replace(/\bA3\b/g, "running on its own")
    .replace(/\brungs\b/gi, (m) => keep(m, "steps")).replace(/\brung\b/gi, (m) => keep(m, "step"));
}

const WORDS = (s: string): number => s.trim().split(/\s+/).filter(Boolean).length;
/** Split a sentence run into what shows (at most `max` words, whole sentences) and the rest, which waits in the evidence. */
export function leadAndRest(text: string | null | undefined, max = 24): { lead: string; rest: string } {
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

/** "Seen about 58 times in 3 weeks." from the engine's own "about 58 times in 3 weeks". An answer with no words is no line. */
export function seenLine(howOften: string | null | undefined): string {
  const t = clip(howOften, 80).replace(/\.$/, "");
  if (!t) return "";
  return /^seen\b/i.test(t) ? `${t}.` : `Seen ${t.charAt(0).toLowerCase()}${t.slice(1)}.`;
}

const trim1 = (n: number): string => n.toFixed(1).replace(/\.0$/, "");
/** The value of a routine as the engine sends it: every part may be missing or odd. */
export type ValueLike = { value?: { hours_saved?: unknown; horizon_weeks?: unknown; net_gbp?: unknown; [k: string]: unknown } | null };
const gbp = (n: number): string => `${n < 0 ? "-" : ""}£${Math.abs(Math.round(n))}`;
/** The two numbers of an interval in order, or null when either is missing, not a number, or the whole range is no saving (a negative estimate is not a saving). */
function hoursRange(v: { hours_saved?: unknown } | null | undefined): [number, number] | null {
  const hs = v?.hours_saved;
  if (!Array.isArray(hs) || hs.length < 2) return null;
  const a = num(hs[0]), b = num(hs[1]);
  if (a === null || b === null) return null;
  const hi = Math.max(a, b);
  return hi <= 0 ? null : [Math.max(0, Math.min(a, b)), hi];
}
/** "Could save 3.1 to 5.2 hours." One range, one quantity. Empty when the engine sent no usable range. */
export function saveLine(r: ValueLike): string {
  const range = hoursRange(r?.value);
  if (!range) return "";
  const [lo, hi] = range;
  if (trim1(lo) === trim1(hi)) return `Could save about ${trim1(hi)} ${trim1(hi) === "1" ? "hour" : "hours"}.`;
  return `Could save ${trim1(lo)} to ${trim1(hi)} hours.`;
}

/** What is behind the "i" beside the hours: the interval and the money, never the only copy of a fact. Any part the engine left out is left out here. */
export function saveHint(r: ValueLike): string {
  const v = r?.value;
  const weeks = num(v?.horizon_weeks);
  const wk = weeks && weeks > 0 ? ` over ${Math.round(weeks)} weeks` : "";
  const net = Array.isArray(v?.net_gbp) && v.net_gbp.length >= 2 ? [num(v.net_gbp[0]), num(v.net_gbp[1])] : null;
  const money = net && net[0] !== null && net[1] !== null ? ` About ${gbp(net[0])} to ${gbp(net[1])} net of set-up.` : "";
  return `95% interval${wk}.${money}`;
}

/** The facts of a routine proposal, each safe to print: the title clipped, a line empty when the engine left its part out, lists that may be empty. */
export function proposalFacts(p: Routine): { title: string; seen: string; save: string; hint: string; touches: string[]; never: string[] } {
  const proposal = (p?.proposal ?? {}) as Partial<Routine["proposal"]>;
  const strings = (x: unknown): string[] => arr<unknown>(x).filter((t): t is string => typeof t === "string" && t.trim() !== "");
  const pick = (a: unknown, b: unknown): string[] => (strings(a).length ? strings(a) : strings(b));
  return {
    title: plainWords(clip(p?.title, 140)) || "A routine",
    seen: seenLine(proposal.how_often),
    save: saveLine(p),
    hint: saveHint(p),
    touches: pick(proposal.touches, p?.touches).map((t) => plainWords(clip(t, 80))),
    never: pick(proposal.never, p?.never).map((n) => plainWords(clip(n, 140)).replace(/\.$/, "")),
  };
}

/** "Touches GovCalc and 3 more." The whole list is one click away. */
export function touchesLead(list: string[], show = 2): { lead: string; more: number } {
  const touches = arr<unknown>(list).filter((t): t is string => typeof t === "string" && t.trim() !== "");
  if (touches.length <= show + 1) return { lead: touches.join(", "), more: 0 };
  const head = touches.slice(0, show);
  return { lead: head.join(", "), more: touches.length - show };
}

/** "It will never submit the case note, send anything to a claimant or open sites you have not used in this routine." Printed whole. */
export function neverLine(list: string[]): string {
  const never = arr<unknown>(list).filter((n): n is string => typeof n === "string" && n.trim() !== "");
  if (never.length === 0) return "";
  const low = never.map((n) => n.charAt(0).toLowerCase() + n.slice(1));
  const body = low.length === 1 ? low[0] : `${low.slice(0, -1).join(", ")} or ${low[low.length - 1]}`;
  return `It will never ${body.replace(/\.$/, "")}.`;
}

/** The overnight report as one line: "Since you were away: 1 run finished, 0 failed." */
export function awayLine(rep: { ran?: unknown[]; failed?: unknown[]; queued?: unknown[]; yielded?: unknown[] } | null): string | null {
  if (!rep) return null;
  const n = arr(rep.ran).length, f = arr(rep.failed).length;
  if (n === 0 && f === 0) return null;
  return `Since you were away: ${n} ${n === 1 ? "run" : "runs"} finished, ${f} failed.`;
}

/**
 * The rows Needs you shows: at least three, and every safety or blocking row; all of them once the worker asks. The first routine proposal is never
 * folded: saying yes or no to a routine is two clicks from Home (Needs you, then Watch first, Not now or Never), however many approvals wait.
 */
export function visibleItems(items: NeedsItem[], showAll: boolean, cap: number = Infinity): NeedsItem[] {
  if (showAll) return items.slice(0, cap);
  const urgent = items.filter((i) => i.cls < 2).length;
  // Hundreds of urgent rows are still safety first, so the first MAX_ROWS are the most urgent; the badge counts them all and the rest are one press away.
  const shown = items.slice(0, Math.min(MAX_ROWS, Math.max(NEEDS_ROWS, urgent)));
  const proposal = items.find((i) => i.kind === "proposal");
  if (!proposal || shown.includes(proposal)) return shown;
  // Make room for it: it takes the place of the last row that is not urgent, or follows the urgent rows when everything shown is urgent.
  const last = shown.length - 1;
  return shown.length > urgent ? [...shown.slice(0, last), proposal] : [...shown, proposal];
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


/** The headline of Needs you: how many things wait. The safety stops are marked on their own rows (and counted by the badge); the headline does not repeat them. Empty when nothing waits. */
export function needsHeadline(items: NeedsItem[]): string {
  const n = items.length;
  if (n === 0) return "";
  return n === 1 ? "1 thing needs you." : `${n} things need you.`;
}
