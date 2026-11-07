import type { CalBlock, CalDay, GapRow, WeekFeatures } from "../types";

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
};
export const featureLabel = (k: string): string => LABEL[k] ?? k.replace(/_/g, " ").replace(/\bh\b/, "(h)").replace(/\bmin\b/, "(min)");

/** Unit from the key: `_h` hours, `_min` minutes, `fragmentation` a 0 to 1 share, anything else a count. */
export function featureUnit(k: string): "h" | "min" | "share" | "count" {
  if (k.endsWith("_h")) return "h";
  if (k.endsWith("_min")) return "min";
  if (k === "fragmentation") return "share";
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
  if (Math.abs(d) < 0.5) return `Your meeting load is about the same as the expert's, ${m} hours a week`;
  return `You spend ${m} hours a week in meetings, ${Math.abs(d)} ${d > 0 ? "more" : "fewer"} than the expert`;
}

/** Does the interval exclude zero? Then the difference is not just noise at this sample size. */
export const gapClear = (r: Pick<GapRow, "ci">): boolean => r.ci[0] > 0 || r.ci[1] < 0;
