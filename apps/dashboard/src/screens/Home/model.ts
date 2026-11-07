// Pure words for Home (docs/knack-ux/01-home.md): the hero sentence, the one line under it, the quiet rows and the quiet-state titles.
// Numbers come from the data; the words are fixed templates. A hero is at most 16 words with one quantity; a row is at most 12 words.
import type { WirePointer, WireWorker } from "../../components/firm/wire";

export const HERO_MAX_WORDS = 16;
export const ROW_MAX_WORDS = 12;
export const TRY_MAX_WORDS = 12;
/** The spec says four, and its own example, "See where the time goes", is five (docs/knack-ux/01-home.md annotation h). The example wins; the lead is asked to record 5. */
export const ACTION_MAX_WORDS = 5;

export const wordCount = (s: string): number => s.trim().split(/\s+/).filter(Boolean).length;

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const parts = (iso: string): [number, number] | null => {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  return m ? [Number(m[3]), Number(m[2]) - 1] : null;
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

/**
 * The hero: "On {step} you usually take about {n} {unit} {longer|less} than {the expert|your peers}." The comma after the step goes, and "the expert's
 * median" becomes "the expert" (the median is behind "Why this?"). A headline of an unknown shape is used as it is, without commas.
 */
export function heroSentence(headline: string): string {
  const s = shapeOf(headline);
  if (!s) return headline.trim().replace(/,/g, "");
  if (s.kind === "gap") return `On ${s.step} you usually take about ${s.n} ${s.unit} ${s.dir} than ${s.who}.`;
  if (s.kind === "better") return `On ${s.step} you now take about ${s.n} ${s.unit} less than a month ago.`;
  return `On ${s.step} you finished ${s.k} of your last ${s.of} cases without help.`;
}

/** The same pointer as a quiet row, at most 12 words: "Reconciling before the note: about 15 seconds longer than the expert." */
export function rowSentence(headline: string): string {
  const s = shapeOf(headline);
  if (!s) return headline.trim().replace(/,/g, "");
  if (s.kind === "gap") return `${upper(s.step)}: about ${s.n} ${s.unit} ${s.dir} than ${s.who}.`;
  if (s.kind === "better") return `${upper(s.step)}: about ${s.n} ${s.unit} less than a month ago.`;
  return `${upper(s.step)}: ${s.k} of ${s.of} cases without help.`;
}

/** The hero's one action, a verb phrase of at most five words, and where it goes. A habit that costs time opens "Where time goes" (Genome). */
export function heroAction(p: Pick<WirePointer, "kind" | "action">): { label: string; href: string } | null {
  if (!p.action) return null;
  const q = p.action.query ? `?${p.action.query}` : "";
  const label = p.kind === "time_loss_habit" ? "See where the time goes"
    : p.kind === "habit_improved" ? "See how it changed"
    : p.kind === "independence_milestone" ? "See your progress"
    : wordCount(p.action.label) <= ACTION_MAX_WORDS ? p.action.label : "See more";
  const to = p.kind === "time_loss_habit" ? "genome" : p.action.to;
  return { label, href: `#/${to}${p.kind === "time_loss_habit" ? "" : q}` };
}

/** What to try, from the engine's own "try" value: imperative, at most 12 words. Absent (null) when the engine has none. */
export function tryLine(t: WireWorker["try"] | undefined): string | null {
  if (!t?.label) return null;
  const label = t.label.trim().replace(/\.$/, "");
  const line = `Try ${label.charAt(0).toLowerCase()}${label.slice(1)}.`;
  return wordCount(line) <= TRY_MAX_WORDS ? line : null;
}

export const EXAMPLE_LINE = "This is an example. Knack starts counting now.";

/* -- Quiet rows --------------------------------------------------------------------------------------------------------------- */

/** "1 thing needs you", "3 things need you". Null at zero: the row is not drawn. */
export function needsLine(n: number): string | null {
  if (n <= 0) return null;
  return n === 1 ? "1 thing needs you" : `${n} things need you`;
}

export interface RepeatsTotal { actions: number; hours_per_week: { point: number; lo: number; hi: number } }

/** "About 1 hour a week could run for you." One rate, no count of repeats. Under an hour it speaks in minutes. Null when nothing repeats. */
export function repeatsRow(t: RepeatsTotal | null | undefined): string | null {
  if (!t || t.actions <= 0) return null;
  const hrs = t.hours_per_week.point;
  if (hrs < 1) return `About ${Math.max(1, Math.round(hrs * 60))} minutes a week could run for you.`;
  const f = String(Math.round(hrs * 10) / 10);
  return `About ${f} ${f === "1" ? "hour" : "hours"} a week could run for you.`;
}

/** The interval behind the row, for its Hint: a 95% interval in hours or minutes a week. */
export function repeatsHint(t: RepeatsTotal | null | undefined): string | null {
  if (!t || t.actions <= 0) return null;
  const minutes = t.hours_per_week.point < 1;
  const f = (h: number): string => (minutes ? String(Math.max(1, Math.round(h * 60))) : String(Math.round(h * 10) / 10));
  return `A 95% interval: ${f(t.hours_per_week.lo)} to ${f(t.hours_per_week.hi)} ${minutes ? "minutes" : "hours"} a week, counted from ${t.actions} of your own repeated steps.`;
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

/* -- The origin badge ---------------------------------------------------------------------------------------------------------- */

/** One origin badge, sentence case: "Example data" when the engine could not answer, else the data's own origin ("Synthetic firm"). Null for real data. */
export function originBadge(opts: { example: boolean; origin: string | null | undefined; badge: string | null | undefined }): string | null {
  if (opts.example) return "Example data";
  if (!opts.origin || opts.origin === "real") return null;
  const b = (opts.badge ?? opts.origin).trim();
  return upper(b.toLowerCase());
}

/* -- The first-week example line ---------------------------------------------------------------------------------------------- */

/** "This is an example. Knack starts counting now." only while an example week stands in and first run finished less than a week ago. */
export function exampleLine(standIn: boolean, firstRunAt: string | null, now = new Date()): string | null {
  if (!standIn || !firstRunAt) return null;
  const t = Date.parse(firstRunAt);
  return Number.isFinite(t) && now.getTime() - t < 7 * 86_400_000 ? EXAMPLE_LINE : null;
}
