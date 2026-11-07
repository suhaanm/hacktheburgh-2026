import type { CalBlock, CalDay, CalPerson, GapRow, RibbonOp, WeekFeatures } from "../types";

/** "HH:MM", minutes since midnight, or an ISO time, all become minutes since midnight. NaN when unreadable. */
export function toMinutes(v: string | number): number {
  if (typeof v === "number") return v;
  const hm = /^(\d{1,2}):(\d{2})/.exec(v.trim());
  if (hm && !/T/.test(v)) return Number(hm[1]) * 60 + Number(hm[2]);
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? NaN : d.getHours() * 60 + d.getMinutes();
}

export interface Span { kind: CalBlock["kind"]; from: number; to: number; attendees?: CalBlock["n_attendees_bucket"] }

/** Blocks as sorted minute spans, with unreadable or empty ones dropped. */
export function spans(blocks: CalBlock[]): Span[] {
  return blocks
    .map((b) => ({ kind: b.kind, from: toMinutes(b.start), to: toMinutes(b.end), attendees: b.n_attendees_bucket }))
    .filter((s) => Number.isFinite(s.from) && Number.isFinite(s.to) && s.to > s.from)
    .sort((a, b) => a.from - b.from);
}

/** The window the ribbon shows: whole hours around every block, never narrower than 08:00 to 18:00. */
export function weekWindow(...weeks: (CalDay[] | undefined)[]): [number, number] {
  let lo = 8 * 60, hi = 18 * 60;
  for (const w of weeks) for (const d of w ?? []) for (const s of spans(d.blocks)) { lo = Math.min(lo, s.from); hi = Math.max(hi, s.to); }
  return [Math.floor(lo / 60) * 60, Math.ceil(hi / 60) * 60];
}

export const DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export const KIND_LABEL: Record<CalBlock["kind"], string> = {
  meeting: "Meeting", focus: "Focus", break: "Break", offscreen: "Off the computer", free: "Free",
};

/** Minutes spent in each kind across a week, for the legend totals and the screen reader. */
export function minutesByKind(days: CalDay[]): Record<CalBlock["kind"], number> {
  const out: Record<CalBlock["kind"], number> = { meeting: 0, focus: 0, break: 0, offscreen: 0, free: 0 };
  for (const d of days) for (const s of spans(d.blocks)) out[s.kind] += s.to - s.from;
  return out;
}

const LABEL: Record<string, string> = {
  meeting_h: "Meeting hours a week",
  focus_blocks_60: "Focus blocks of an hour or more",
  focus_blocks_90: "Focus blocks of 90 minutes or more",
  longest_focus_min: "Longest focus block",
  fragmentation: "Fragmentation (0 solid, 1 chopped up)",
  back_to_back_runs: "Back-to-back meeting runs",
  work_span_h: "Working day, start to finish",
  offscreen_h: "Time off the computer",
  meeting_share: "Share of the working week in meetings",
  fragmented_days: "Days chopped into slivers",
  recurring_in_peak_h: "Recurring meetings in peak hours (h)",
  external_unbuffered_n: "External meetings with no buffer",
  review_slots: "Short review slots",
  batch_windows: "Batch windows for similar work",
  outside_hours_h: "Hours outside working hours",
  meetings_n: "Meetings",
  focus_h: "Focus hours a week",
};
export const featureLabel = (k: string): string => LABEL[k] ?? k.replace(/_/g, " ").replace(/\bh\b/, "(h)").replace(/\bmin\b/, "(min)").replace(/^./, (c) => c.toUpperCase());

/** Unit from the key: `_h` hours, `_min` minutes, `fragmentation` a 0 to 1 share, anything else a count. */
export function featureUnit(k: string): "h" | "min" | "share" | "count" {
  if (k.endsWith("_h")) return "h";
  if (k.endsWith("_min")) return "min";
  if (k === "fragmentation" || k.endsWith("_share")) return "share";
  return "count";
}

export function fmtFeature(k: string, v: number, signed = false): string {
  const u = featureUnit(k);
  const sign = signed && v > 0 ? "+" : signed && v < 0 ? "−" : "";
  const a = Math.abs(v);
  const n = u === "share" ? a.toFixed(2) : u === "count" ? (Number.isInteger(a) ? String(a) : a.toFixed(1)) : Number.isInteger(a) ? String(a) : a.toFixed(1);
  return `${signed ? sign : v < 0 ? "−" : ""}${n}${u === "h" ? " h" : u === "min" ? " min" : ""}`;
}

/** The headline: how the learner's meeting load compares with the expert's, in words. */
export function weekHeadline(f: WeekFeatures, e: WeekFeatures): string {
  const m = f.meeting_h, em = e.meeting_h;
  if (typeof m !== "number" || typeof em !== "number") return "Your week against the expert's";
  const d = Math.round((m - em) * 10) / 10;
  const mr = Math.round(m * 10) / 10;
  if (Math.abs(d) < 0.5) return `Your meeting load is about the same as the expert's, ${mr} hours a week`;
  return `You spend ${mr} hours a week in meetings, ${Math.abs(d)} ${d > 0 ? "more" : "fewer"} than the expert`;
}

/** Does the interval exclude zero? Then the difference is not just noise at this sample size. The engine's own verdict, when it sends one, wins. */
export const gapClear = (r: Pick<GapRow, "ci"> & { significant?: boolean }): boolean => (typeof r.significant === "boolean" ? r.significant : r.ci[0] > 0 || r.ci[1] < 0);

/** How big a gap is next to the spread experts show among themselves: the distance from the expert mean in units of the expert range's width. */
export function gapSize(r: Pick<GapRow, "delta" | "expert_range">): number {
  const w = r.expert_range ? r.expert_range[1] - r.expert_range[0] : 0;
  return w > 0 ? Math.abs(r.delta) / w : Math.abs(r.delta);
}

/** Clear gaps first, the biggest first (by how many expert-ranges away); the rest keep the engine's order. */
export function sortGaps<T extends Pick<GapRow, "delta" | "ci" | "expert_range"> & { significant?: boolean }>(rows: T[]): T[] {
  const idx = new Map(rows.map((r, i) => [r, i]));
  return [...rows].sort((a, b) => Number(gapClear(b)) - Number(gapClear(a)) || (gapClear(a) && gapClear(b) ? gapSize(b) - gapSize(a) : (idx.get(a) ?? 0) - (idx.get(b) ?? 0)));
}

export interface AlignmentTotals { total: number; matched: number; mismatch: number; learnerOnly: number; expertOnly: number; outOfStep: number }
/** Minutes in each kind of column of the week alignment. `learnerOnly` is time you spend that the expert's week has no counterpart for; `expertOnly` is the reverse. */
export function alignmentTotals(alignment: RibbonOp[]): AlignmentTotals {
  const t: AlignmentTotals = { total: 0, matched: 0, mismatch: 0, learnerOnly: 0, expertOnly: 0, outOfStep: 0 };
  for (const c of alignment) {
    const m = Number.isFinite(c.minutes) ? Math.max(0, c.minutes) : 0;
    t.total += m;
    if (c.op === "match") t.matched += m;
    else if (c.op === "mismatch") t.mismatch += m;
    else if (c.op === "gap_expert") t.learnerOnly += m;
    else if (c.op === "gap_novice") t.expertOnly += m;
  }
  t.outOfStep = t.mismatch + t.learnerOnly + t.expertOnly;
  return t;
}

/** The people who have a week to show, learners first: personas, then novices, then experts. */
export function peopleByGroup(people: CalPerson[]): { group: string; label: string; people: CalPerson[] }[] {
  const order: [string, string][] = [["persona", "Demo people"], ["novice", "Novices"], ["expert", "Experts"]];
  const out = order.map(([g, label]) => ({ group: g, label, people: people.filter((p) => p.group === g) })).filter((x) => x.people.length);
  const known = new Set(order.map(([g]) => g));
  const rest = people.filter((p) => !known.has(p.group ?? ""));
  if (rest.length) out.push({ group: "other", label: "Others", people: rest });
  return out;
}

/** "2026-W44" as "week 44". Anything else is shown as it came. */
export function weekLabel(w: string): string {
  const m = /^(\d{4})-W(\d{1,2})$/.exec(w);
  return m ? `Week ${Number(m[2])}, ${m[1]}` : w;
}

export const OP_LABEL: Record<string, string> = {
  match: "Same as the expert",
  mismatch: "Different from the expert",
  gap_expert: "Only in your week",
  gap_novice: "Only in the expert's week",
};

const ENUM_LABEL: Record<string, string> = { MEETING: "meeting", FOCUS: "focus", SLIVER: "short gap", REVIEW: "review", OFFSCREEN: "off screen", BREAK: "break", FREE: "free" };
/** The engine's block-kind enums in plain words. */
export const enumLabel = (e: string | null): string => (e == null ? "nothing" : ENUM_LABEL[e] ?? e.toLowerCase().replace(/_/g, " "));
