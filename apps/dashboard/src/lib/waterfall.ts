import type { Interval, WaterfallStep } from "../types";

export interface WaterfallRow {
  label: string;
  seconds: number;
  ci: Interval;
  start: number;
  end: number;
  /** Whisker around the end of the bar: where the cumulative total could sit given this step's interval. */
  whisker: Interval;
  total: boolean;
}

/** Largest steps first, "small differences" style catch-alls last; cumulative bars with interval whiskers. */
export function layoutWaterfall(steps: WaterfallStep[], totalCi?: Interval): { rows: WaterfallRow[]; total: number; max: number; min: number } {
  const isOther = (l: string) => /small|other|elsewhere/i.test(l);
  const ordered = [...steps].sort((a, b) => {
    if (isOther(a.label) !== isOther(b.label)) return isOther(a.label) ? 1 : -1;
    return b.seconds - a.seconds;
  });
  let cum = 0;
  const rows: WaterfallRow[] = ordered.map((s) => {
    const start = cum;
    cum += s.seconds;
    return { label: s.label, seconds: s.seconds, ci: s.ci, start, end: cum, whisker: [cum - (s.seconds - s.ci[0]), cum + (s.ci[1] - s.seconds)], total: false };
  });
  const total = cum;
  const tci: Interval = totalCi ?? [total, total];
  rows.push({ label: "Time lost in total", seconds: total, ci: tci, start: 0, end: total, whisker: tci, total: true });
  const max = Math.max(...rows.map((r) => Math.max(r.whisker[1], r.start, r.end)), total);
  const min = Math.min(0, ...rows.map((r) => Math.min(r.whisker[0], r.start, r.end)));
  return { rows, total, max, min };
}
