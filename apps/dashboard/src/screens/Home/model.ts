// Pure words for Home (docs/knack-ux/01-home.md): the hero sentence, the one line under it, the quiet rows and the quiet-state titles.
// Numbers come from the data; the words are fixed templates. A hero is at most 16 words with one quantity; a row is at most 12 words.
import type { WirePointer, WireWorker } from "../../components/firm/wire";
import { shortTaskName } from "../../lib/coach";

export const HERO_MAX_WORDS = 16;
export const ROW_MAX_WORDS = 12;
export const TRY_MAX_WORDS = 12;
/** The spec says four, and its own example, "See where the time goes", is five (docs/knack-ux/01-home.md annotation h). The example wins; the lead is asked to record 5. */
export const ACTION_MAX_WORDS = 5;

export const wordCount = (s: string): number => s.trim().split(/\s+/).filter(Boolean).length;

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
/** [day, month index] read from the date part of an ISO string, as written (no time zone shifts the day). A date that is not a real calendar date is null. */
const parts = (iso: string): [number, number] | null => {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(typeof iso === "string" ? iso : "");
  if (!m) return null;
  const month = Number(m[2]), day = Number(m[3]);
  if (month < 1 || month > 12 || day < 1 || day > 31) return null;
  return [day, month - 1];
};

/** "Week of 9 November", from the first day of the week. Null when the date cannot be read. */
export function weekOf(week: WireWorker["week"]): string | null {
  const a = week ? parts(week.from) : null;
  return a ? `Week of ${a[0]} ${MONTHS[a[1]]}` : null;
}

/** "9 to 15 November", or "30 November to 6 December" when the week crosses a month. Null when the dates cannot be read. */
export function weekLabel(week: WireWorker["week"]): string | null {
  if (!week) return null;
  const a = parts(week.from), b = parts(week.to);
  if (!a || !b) return null;
  return a[1] === b[1] ? `${a[0]} to ${b[0]} ${MONTHS[b[1]]}` : `${a[0]} ${MONTHS[a[1]]} to ${b[0]} ${MONTHS[b[1]]}`;
}

/* -- Numbers and their units ------------------------------------------------------------------------------------------------ */

const SINGULAR: Record<string, string> = { seconds: "second", minutes: "minute", hours: "hour", days: "day", steps: "step", cases: "case", times: "time" };
const fmtInt = (n: number): string => Math.round(n).toLocaleString("en-GB");

/**
 * A measure as the worker reads it: "35 seconds", "1 second", "20 minutes" (120 seconds or more is said in minutes, 120 minutes or more in hours), thousands with a
 * separator. The engine's unit word is kept; only its number and plural change. A value that is not a number is null (the sentence is then used as the engine wrote it).
 */
export function measure(n: number | string, unit: string): { n: string; unit: string } | null {
  const v = typeof n === "string" ? (n.trim() === "" ? Number.NaN : Number(n)) : n;
  if (typeof v !== "number" || !Number.isFinite(v)) return null;
  let value = v, u = unit.toLowerCase();
  if (u === "seconds" && value >= 120) { value /= 60; u = "minutes"; }
  if (u === "minutes" && value >= 120) { value /= 60; u = "hours"; }
  const shown = u === "hours" && value < 100 ? String(Math.round(value * 10) / 10) : fmtInt(value);
  const one = shown === "1";
  return { n: shown, unit: one ? (SINGULAR[u] ?? u) : (Object.entries(SINGULAR).find(([, sg]) => sg === u)?.[0] ?? u) };
}

/* -- The hero sentence ------------------------------------------------------------------------------------------------------ */

const upper = (s: string): string => s.charAt(0).toUpperCase() + s.slice(1);

type Shape =
  | { kind: "gap"; step: string; n: string; unit: string; dir: "longer" | "less"; who: string }
  | { kind: "better"; step: string; n: string; unit: string }
  | { kind: "milestone"; step: string; k: string; of: string };

/** The engine's three fixed headline templates, read back into their parts. Null for a headline of any other shape. */
export function shapeOf(headline: string): Shape | null {
  const h = headline.trim().replace(/\s+/g, " ");
  let m = /^On (.+?),? you usually take about (\d+) (\w+) (longer|less) than (the expert's median|the expert|your peers)\.?$/.exec(h);
  if (m) return { kind: "gap", step: m[1], n: m[2], unit: m[3], dir: m[4] as "longer" | "less", who: m[5] === "your peers" ? "your peers" : "the expert" };
  m = /^On (.+?),? you now take about (\d+) (\w+) less than you did a month ago\.?$/.exec(h);
  if (m) return { kind: "better", step: m[1], n: m[2], unit: m[3] };
  m = /^On (.+?),? you finished (\d+) of your last (\d+) cases without help\.?$/.exec(h);
  if (m) return { kind: "milestone", step: m[1], k: m[2], of: m[3] };
  return null;
}

const clip = (step: string, max: number): string => {
  const w = step.trim().split(/\s+/);
  return w.length <= max ? step.trim() : `${w.slice(0, max).join(" ")}\u2026`;
};

function heroText(s: Shape, step: string, usually: boolean): string {
  if (s.kind === "gap") {
    const m = measure(s.n, s.unit);
    if (!m) return "";
    if (Number(s.n) === 0) return `On ${step} you take about as long as ${s.who}.`;
    return `On ${step} you ${usually ? "usually " : ""}take about ${m.n} ${m.unit} ${s.dir} than ${s.who}.`;
  }
  if (s.kind === "better") {
    const m = measure(s.n, s.unit);
    return m ? `On ${step} you now take about ${m.n} ${m.unit} less than a month ago.` : "";
  }
  return `On ${step} you finished ${s.k} of your last ${s.of} cases without help.`;
}

/**
 * The hero: "On {step} you usually take about {n} {unit} {longer|less} than {the expert|your peers}." The comma after the step goes, and "the expert's
 * median" becomes "the expert" (the median is behind "Why this?"). It stays within 16 words: "usually" goes first, then a long step is cut to its
 * first words. A headline of an unknown shape is used as it is, without commas.
 */
export function heroSentence(headline: string): string {
  const s = shapeOf(headline);
  if (!s) return headline.trim().replace(/,/g, "");
  for (const [usually, max] of [[true, 99], [false, 99], [false, 8], [false, 5]] as const) {
    const t = heroText(s, clip(s.step, max), usually);
    if (!t) return headline.trim().replace(/,/g, "");
    if (wordCount(t) <= HERO_MAX_WORDS) return t;
  }
  return heroText(s, clip(s.step, 3), false);
}

/** The same pointer as a quiet row, at most 12 words: "Reconciling before the note: about 15 seconds longer than the expert." */
export function rowSentence(headline: string): string {
  const s = shapeOf(headline);
  if (!s) return headline.trim().replace(/,/g, "");
  for (const max of [99, 6, 4]) {
    const step = upper(clip(s.step, max));
    let t: string;
    if (s.kind === "milestone") t = `${step}: ${s.k} of ${s.of} cases without help.`;
    else {
      const m = measure(s.n, s.unit);
      if (!m) return headline.trim().replace(/,/g, "");
      t = s.kind === "gap" && Number(s.n) === 0 ? `${step}: about as long as ${s.who}.` : s.kind === "gap" ? `${step}: about ${m.n} ${m.unit} ${s.dir} than ${s.who}.` : `${step}: about ${m.n} ${m.unit} less than a month ago.`;
    }
    if (wordCount(t) <= ROW_MAX_WORDS || max === 4) return t;
  }
  return headline.trim().replace(/,/g, "");
}

/** The hero's one action, a verb phrase of at most five words, and where it goes. A habit that costs time opens "Where time goes" (Genome). */
export function heroAction(p: Pick<WirePointer, "kind" | "action">): { label: string; href: string } | null {
  if (!p.action) return null;
  const q = p.action.query ? `?${p.action.query}` : "";
  const label = p.kind === "time_loss_habit" ? "See where the time goes"
    : p.kind === "habit_improved" ? "See how it changed"
    : p.kind === "independence_milestone" ? "See your progress"
    : wordCount(p.action.label) <= ACTION_MAX_WORDS ? p.action.label : "See more";
  if (p.kind === "time_loss_habit") return { label, href: "#/growth?section=steps" };
  return { label, href: `#/${p.action.to}${q}` };
}

/** What to try, from the engine's own "try" value: imperative, at most 12 words. Absent (null) when the engine has none. */
export function tryLine(t: WireWorker["try"] | undefined): string | null {
  if (!t?.label) return null;
  const label = t.label.trim().replace(/\.$/, "");
  if (!/[\p{L}\p{N}]/u.test(label)) return null;
  const line = `Try ${label.charAt(0).toLowerCase()}${label.slice(1)}.`;
  return wordCount(line) <= TRY_MAX_WORDS ? line : null;
}

/* -- Quiet rows --------------------------------------------------------------------------------------------------------------- */

/** "1 thing needs you", "3 things need you". Null at zero: the row is not drawn. */
export function needsLine(n: number): string | null {
  const v = Math.floor(n);
  if (!Number.isFinite(v) || v <= 0) return null;
  return v === 1 ? "1 thing needs you" : `${v.toLocaleString("en-GB")} things need you`;
}

export interface RepeatsTotal { actions: number; hours_per_week: { point: number; lo: number; hi: number } }

const okTotal = (t: RepeatsTotal | null | undefined): t is RepeatsTotal => !!t && Number.isFinite(t.actions) && t.actions > 0 && !!t.hours_per_week && Number.isFinite(t.hours_per_week.point) && t.hours_per_week.point > 0;

/** "About 1 hour a week could run for you." One rate, no count of repeats. Under an hour it speaks in minutes. Null when nothing repeats or the rate is not a positive number. */
export function repeatsRow(t: RepeatsTotal | null | undefined): string | null {
  if (!okTotal(t)) return null;
  const hrs = t.hours_per_week.point;
  if (hrs < 1) return `About ${Math.max(1, Math.round(hrs * 60))} minutes a week could run for you.`;
  const f = hrs >= 100 ? Math.round(hrs).toLocaleString("en-GB") : String(Math.round(hrs * 10) / 10);
  return `About ${f} ${f === "1" ? "hour" : "hours"} a week could run for you.`;
}

/** The interval behind the row, for its Hint: a 95% interval in hours or minutes a week. Null when the interval is missing or not numbers. */
export function repeatsHint(t: RepeatsTotal | null | undefined): string | null {
  if (!okTotal(t)) return null;
  const { lo, hi } = t.hours_per_week;
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return null;
  const minutes = t.hours_per_week.point < 1;
  const f = (h: number): string => (minutes ? String(Math.max(1, Math.round(h * 60))) : String(Math.round(Math.max(0, h) * 10) / 10));
  return `A 95% interval: ${f(Math.min(lo, hi))} to ${f(Math.max(lo, hi))} ${minutes ? "minutes" : "hours"} a week, counted from ${Math.round(t.actions).toLocaleString("en-GB")} of your own repeated steps.`;
}

export const GROWTH_ROW = "See how much less help you need.";

/* -- Quiet states ------------------------------------------------------------------------------------------------------------- */

export type QuietKind = "learning" | "nothing" | "stale" | "role_changed" | "set_up" | "error";
export interface Quiet { kind: QuietKind; title: string; body: string; action: "try-again" | "choose-role" | null }

/** The wording of every state that is not a normal week (docs/knack-ux/01-home.md). Each says what happened, then what is true. */
export function quietFor(status: string, opts: { setUp: boolean } = { setUp: true }): Quiet {
  if (status === "onboarding" || status === "no_data") {
    return opts.setUp
      ? { kind: "learning", title: "Knack is learning your work.", body: "Check back in a few days.", action: null }
      : { kind: "set_up", title: "Choose your role first.", body: "Knack starts counting after that.", action: "choose-role" };
  }
  if (status === "stale") return { kind: "stale", title: "These numbers are out of date.", body: "Knack says nothing rather than something old.", action: "try-again" };
  if (status === "role_changed") return { kind: "role_changed", title: "Your role changed.", body: "Pointers start again, so you are not compared with your old role.", action: null };
  return { kind: "nothing", title: "Nothing stands out this week.", body: "No number moved far enough to matter.", action: null };
}
export const COULD_NOT_LOAD: Quiet = { kind: "error", title: "Could not read your week.", body: "Nothing was changed.", action: "try-again" };

/* -- The coaching row -------------------------------------------------------------------------------------------------------------- */

export interface CoachTaskLike { name?: unknown; step?: unknown; steps_total?: unknown }

/**
 * "Coaching: Entitlement check." while a coach step is really active, else null (the row is not drawn). The task name is cut at its first comma or colon
 * ("Entitlement check, household H-9" is the task; the household is not part of the sentence), at most nine words: a lesson name such as "Read the failing
 * trace before changing code" reads as it is, which "Coaching you on ..." could not carry. A step that is not a positive whole number, or one past the last,
 * is not active; `active === false` (the engine says no task is open) is not active either, whatever step it names. Never throws: the coach state is whatever
 * the service sent.
 */
export function coachLine(task: CoachTaskLike | null | undefined, active?: boolean | null): string | null {
  if (active === false) return null;
  if (!task || typeof task.name !== "string") return null;
  const step = Number(task.step), total = Number(task.steps_total);
  if (!Number.isInteger(step) || step < 1 || (Number.isInteger(total) && total >= 1 && step > total)) return null;
  const name = shortTaskName(task.name);
  if (!/[\p{L}\p{N}]/u.test(name)) return null;
  return `Coaching: ${name}${name.endsWith("…") ? "" : "."}`;
}
