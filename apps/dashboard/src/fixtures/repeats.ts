/**
 * Example data for the Repeats page, shown (and badged "example data") only when the engine is off or cannot be reached. A small made-up
 * benefits-processor week built the way the engine builds it: counts per week scaled to the window, minutes = repeats a week x time a run
 * x (1 - judgement share), an interval from the count. Nothing here is measured from anyone.
 */
import type { AnalyticMeta } from "../types";
import type { Est, FirmRow, FirmWire, HitRow, HitlistWire, HitState, HitStatus, Stops } from "../components/repeats/types";

interface Base {
  id: string; label: string; key: string; family: HitRow["family"]; perWeek: number; minPerRun: number; judgement: number; stops: Stops; status: HitStatus;
  what: string; touches: string[]; never: string[]; can?: boolean; overlaps?: HitRow["overlaps"];
}

const BASE: Base[] = [
  { id: "calc-entry-3x", label: "Enter the household into three calculators", key: "household", family: "enter", perWeek: 15, minPerRun: 3.9, judgement: 0.1, stops: "submit", status: "proposed",
    what: "Enter the household into all three calculators and read back each result, then stop.", touches: ["GovCalc", "Quick Estimator", "EntitledTo", "case note"], never: ["submit", "submit to claimant record"] },
  { id: "case-note-copy", label: "Copy the agreed results into the case note", key: "agreed results", family: "copy", perWeek: 11, minPerRun: 1.4, judgement: 0, stops: "submit", status: "learning",
    what: "Copy each calculator's result into the case note and save it as a draft. It never presses Submit to claimant record.", touches: ["case note"], never: ["submit", "submit to claimant record", "send letter"] },
  { id: "open-next-case", label: "Open the next case from the queue", key: "next case", family: "open", perWeek: 9, minPerRun: 0.9, judgement: 0, stops: "none", status: "candidate",
    what: "Open the next case in your queue and stop on its first page.", touches: ["case queue"], never: ["submit", "close case"],
    overlaps: [{ id: "open-previous-case", label: "Open the previous case from the queue", relation: "includes" }] },
  { id: "paste-review-sheet", label: "Paste the result figures into the review sheet", key: "result figures", family: "copy", perWeek: 7, minPerRun: 1.6, judgement: 0, stops: "none", status: "running",
    what: "Paste the three result figures into the next free row of the review sheet.", touches: ["review sheet"], never: ["send email", "export"] },
  { id: "reconcile-totals", label: "Reconcile the three results and flag differences", key: "three results", family: "check", perWeek: 6, minPerRun: 2.8, judgement: 0.3, stops: "none", status: "candidate",
    what: "Line the three results up and mark any that differ by more than a pound a week. It does not decide which is right.", touches: ["GovCalc", "Quick Estimator", "EntitledTo"], never: ["submit"] },
  { id: "save-draft-letter", label: "Save the draft letter to the case folder", key: "draft letter", family: "enter", perWeek: 4.5, minPerRun: 2.1, judgement: 0, stops: "message", status: "candidate",
    what: "Fill the letter template from the case note and save it as a draft. It never sends it.", touches: ["letter template", "case folder"], never: ["send letter", "send email"] },
  { id: "export-weekly-figures", label: "Export the weekly figures for the team", key: "weekly figures", family: "copy", perWeek: 3.4, minPerRun: 5.5, judgement: 0.1, stops: "share", status: "candidate",
    what: "Collect the week's figures into the team sheet. It never shares or sends it.", touches: ["case system", "team sheet"], never: ["export", "share"] },
  { id: "log-call", label: "Log the call in the contact record", key: "contact record", family: "enter", perWeek: 3.2, minPerRun: 1.1, judgement: 0, stops: "none", status: "candidate",
    what: "Add a dated line to the contact record for the case you just closed the call on.", touches: ["contact record"], never: ["delete", "overwrite"] },
];

const AUTOMATED: Base = { id: "copy-case-ref", label: "Copy the case reference into the note", key: "case reference", family: "copy", perWeek: 21, minPerRun: 0.4, judgement: 0, stops: "none",
  status: "automated", what: "Copy the case reference into the first line of the note.", touches: ["case note"], never: ["submit"] };

const T = Date.UTC(2026, 10, 7, 16, 40) / 1000;
const iso = (s: number) => new Date(s * 1000).toISOString().replace(/\.\d{3}Z$/, "Z");

function est(point: number, count: number): Est {
  const half = (1.96 * point) / Math.sqrt(Math.max(count, 1)) * 1.05;
  return { point: round1(point), lo: round1(Math.max(0, point - half)), hi: round1(point + half) };
}
const round1 = (n: number) => Math.round(n * 10) / 10;

function rowOf(b: Base, windowDays: 7 | 30, n: number): HitRow | null {
  const weeks = windowDays / 7;
  const count = Math.round(b.perWeek * weeks);
  if (count < 3) return null;
  const point = (count / weeks) * b.minPerRun * (1 - b.judgement);
  return {
    id: b.id, label: b.label, key: b.key, family: b.family, count, minutes_per_week: est(point, count), judgement_share: b.judgement, status: b.status,
    stops_before: b.stops, variation: 0.06, variants: 1, overlaps: b.overlaps ?? [], seconds_per_time: Math.round(b.minPerRun * 60), t: T - n * 5400,
    actions: { routine_id: b.id, can_automate: b.can !== false, card_id: `c_example${String(n).padStart(2, "0")}` },
    what: b.what, touches: b.touches, never: b.never,
  };
}

function totalOf(rows: HitRow[]): HitlistWire["total"] {
  if (!rows.length) return null;
  const pt = rows.reduce((a, r) => a + r.minutes_per_week.point, 0);
  const half = Math.sqrt(rows.reduce((a, r) => a + ((r.minutes_per_week.hi - r.minutes_per_week.lo) / 2) ** 2, 0));
  const m = { point: round1(pt), lo: round1(pt - half), hi: round1(pt + half) };
  const h = (x: number) => Math.round((x / 60) * 100) / 100;
  return { actions: rows.length, repeats: rows.reduce((a, r) => a + r.count, 0), minutes_per_week: m, hours_per_week: { point: h(pt), lo: h(pt - half), hi: h(pt + half) } };
}

export const EXAMPLE_META: AnalyticMeta = {
  origin: "synthetic", n: 306, n_unit: "episodes", split: null, interval_level: 0.95, generated_at: iso(T),
  note: "Counts come from this device's own record of your work. Minutes are estimates with a 95% interval. Nothing runs unless you press Automate.",
};

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
/** "2026-11-07" as "7 November". */
export const humanDate = (iso: string): string => { const [, m, d] = iso.slice(0, 10).split("-").map(Number); return m && d ? `${d} ${MONTHS[m - 1]}` : iso; };

export const SENTENCES = {
  new_user: "Nothing to count yet. Work as you normally do, and when the same steps come up three times they will appear here.",
  too_little: (n: number, w: number) => `Only ${n} ${n === 1 ? "case" : "cases"} in the last ${w} days, too few to tell what repeats.` + (w < 30 ? " Try the 30 day view, or check back after a few more working days." : " Check back after a few more working days."),
  nothing: (w: number) => `Nothing has repeated three times in the last ${w} days in a way that could be automated.`,
  all_handled: "Everything that repeats is already handled, hidden, or needs your judgement.",
  counting_again: (since: string) => `Counting again since ${humanDate(since)}. Rows come back when the same steps repeat three times.`,
  capture_off: "Capture is off, so nothing is being counted. Turn it on in your memory file, under Preferences, if you want this list.",
};

export type ExampleKind = "ok" | HitState;

export interface ExampleOpts { hidden?: Set<string>; reset?: boolean; status?: Record<string, HitStatus>; kind?: ExampleKind }

/** What the engine would send for the example week. `opts` carries what the worker did to it in this session (hid a row, started counting again, set one to watch). */
export function exampleHitlist(windowDays: 7 | 30, opts: ExampleOpts = {}): HitlistWire {
  const base: HitlistWire = {
    state: "ok", message: "", window_days: windowDays, window_from: iso(T - windowDays * 86400), window_to: iso(T), counting_since: null,
    episodes_in_window: windowDays === 7 ? 306 : 768, rows: [], automated: [], hidden: [], held_back: [{ reason: "judgement", count: 2 }, { reason: "irreversible_first_step", count: 1 }],
    not_shown: 0, total: null,
  };
  const empty = (state: HitState, message: string, n = base.episodes_in_window): HitlistWire => ({ ...base, state, message, episodes_in_window: n, held_back: [] });
  const kind = opts.kind ?? "ok";
  if (kind === "new_user") return empty("new_user", SENTENCES.new_user, 0);
  if (kind === "too_little_data") return empty("too_little_data", SENTENCES.too_little(4, windowDays), 4);
  if (kind === "nothing_repeats") return empty("nothing_repeats", SENTENCES.nothing(windowDays));
  if (kind === "all_handled") return { ...empty("all_handled", SENTENCES.all_handled), automated: [rowOf(AUTOMATED, windowDays, 9)!] };
  if (kind === "capture_off") return empty("capture_off", SENTENCES.capture_off, 0);
  if (opts.reset || kind === "counting_again") return { ...empty("counting_again", SENTENCES.counting_again(iso(T).slice(0, 10)), 0), counting_since: iso(T) };
  const hidden = opts.hidden ?? new Set<string>();
  const rank = (a: HitRow, b: HitRow) => b.minutes_per_week.point - a.minutes_per_week.point || b.count - a.count || a.id.localeCompare(b.id);       // the engine's order
  const rows = BASE.map((b, i) => rowOf(b, windowDays, i)).filter((r): r is HitRow => !!r)
    .map((r) => (opts.status?.[r.id] ? { ...r, status: opts.status[r.id] } : r)).sort(rank);
  const shown = rows.filter((r) => !hidden.has(r.id));
  const hid = rows.filter((r) => hidden.has(r.id)).map((r) => ({ id: r.id, label: r.label, count: r.count, returns_at: r.count * 2 }));
  const seeded = { id: "print-cover-sheet", label: "Print the cover sheet", count: Math.round(4 * windowDays / 7), returns_at: Math.round(8 * windowDays / 7) };
  const autos = [rowOf(AUTOMATED, windowDays, 9)!];
  return { ...base, rows: shown, automated: autos, hidden: [...hid, ...(hidden.has(seeded.id) ? [] : [seeded])].sort((a, b) => b.count - a.count || a.id.localeCompare(b.id)), total: totalOf(shown) };
}

/** The example firm: three roles, about 60 people, a group of fewer than five not listed. */
export function exampleFirm(windowDays: 7 | 30): FirmWire {
  const w = windowDays / 7;
  const mk = (id: string, label: string, key: string, family: FirmRow["family"], role: string, people: number, perPersonWeek: number, minPerRun: number, stops: Stops): FirmRow => {
    const count = Math.round(people * perPersonWeek * w);
    const pt = people * perPersonWeek * minPerRun;
    const half = (1.96 * pt) / Math.sqrt(count) * 0.55;
    const h = (x: number) => Math.round((x / 60) * 100) / 100;
    return { id, label, key, family, role, people, count, minutes_per_week: { point: round1(pt), lo: round1(pt - half), hi: round1(pt + half) },
      hours_per_week: { point: h(pt), lo: h(pt - half), hi: h(pt + half) }, stops_before: stops };
  };
  const rows = [
    mk("calc-entry-3x", "Enter the household into three calculators", "household", "enter", "benefits-processor", 32, 14, 3.9, "submit"),
    mk("case-note-copy", "Copy the agreed results into the case note", "agreed results", "copy", "benefits-processor", 28, 9, 1.4, "submit"),
    mk("rerun-failed-ci", "Re-run a failed CI job and read the result", "failed CI job", "run", "programmer", 10, 6, 3, "release"),
    mk("weekly-metric-refresh", "Refresh the weekly metrics sheet", "weekly metrics sheet", "run", "data-analyst", 9, 1.2, 12, "share"),
  ].sort((a, b) => b.minutes_per_week.point - a.minutes_per_week.point);
  const pt = rows.reduce((a, r) => a + r.hours_per_week.point, 0);
  const half = Math.sqrt(rows.reduce((a, r) => a + ((r.hours_per_week.hi - r.hours_per_week.lo) / 2) ** 2, 0));
  return { window_days: windowDays, people: 60, min_group: 5, suppressed: 1, not_shown: 0, rows,
    total: { actions: rows.length, people: 60, hours_per_week: { point: round1(pt), lo: round1(pt - half), hi: round1(pt + half) } } };
}
