import type { PresenceBin, QuietHours } from "../types";

/** Five classes, matching --seq-0 .. --seq-4 in the design tokens. */
export const HEAT_CLASSES = [
  { q: 0, lo: 0, hi: 0.1, label: "under 10%" },
  { q: 1, lo: 0.1, hi: 0.3, label: "10 to 30%" },
  { q: 2, lo: 0.3, hi: 0.5, label: "30 to 50%" },
  { q: 3, lo: 0.5, hi: 0.75, label: "50 to 75%" },
  { q: 4, lo: 0.75, hi: 1.0001, label: "over 75%" },
];

export function quantize(p: number): number {
  for (const c of HEAT_CLASSES) if (p >= c.lo && p < c.hi) return c.q;
  return 4;
}

/** An interval wider than this is hatched on the map. */
export const WIDE_INTERVAL = 0.4;
export const isWide = (b: Pick<PresenceBin, "lo" | "hi">) => b.hi - b.lo > WIDE_INTERVAL;

export function toGrid(bins: PresenceBin[]): (PresenceBin | null)[][] {
  const grid: (PresenceBin | null)[][] = Array.from({ length: 7 }, () => Array<PresenceBin | null>(96).fill(null));
  for (const b of bins) if (b.dow >= 0 && b.dow < 7 && b.slot >= 0 && b.slot < 96) grid[b.dow][b.slot] = b;
  return grid;
}

export function parseClock(s: string): number {
  const m = /^(\d{1,2}):(\d{2})$/.exec(s.trim());
  if (!m) return NaN;
  const h = Number(m[1]), mm = Number(m[2]);
  if (h > 24 || mm > 59) return NaN;
  return (h * 60 + mm) / 15;
}

/** Slot ranges [from, to) inside a day that fall in quiet hours. A window past midnight yields two. */
export function quietSegments(q: QuietHours, dow: number): [number, number][] {
  if (!q.days.includes(dow)) return [];
  const a = parseClock(q.start), b = parseClock(q.end);
  if (Number.isNaN(a) || Number.isNaN(b) || a === b) return [];
  return a < b ? [[a, b]] : [[a, 96], [0, b]].filter(([x, y]) => y > x) as [number, number][];
}

export function inQuiet(q: QuietHours, dow: number, slot: number): boolean {
  return quietSegments(q, dow).some(([a, b]) => slot >= a && slot < b);
}

/** Plain-language read of the busiest stretch of a day, for the screen reader and the caption. */
export function busiestStretch(row: (PresenceBin | null)[], threshold = 0.5): [number, number] | null {
  let best: [number, number] | null = null;
  let start = -1;
  for (let s = 0; s <= row.length; s++) {
    const on = s < row.length && (row[s]?.p ?? 0) >= threshold;
    if (on && start < 0) start = s;
    if (!on && start >= 0) {
      if (!best || s - start > best[1] - best[0]) best = [start, s];
      start = -1;
    }
  }
  return best;
}

/** Mean probability per slot across the given days (all days by default). */
export function meanRow(grid: (PresenceBin | null)[][], days: number[] = [0, 1, 2, 3, 4, 5, 6]): number[] {
  return Array.from({ length: 96 }, (_, s) => {
    const v = days.map((d) => grid[d]?.[s]?.p).filter((x): x is number => x != null);
    return v.length ? v.reduce((a, b) => a + b, 0) / v.length : 0;
  });
}

/** Longest stretch at or above `thr` in a 24-hour cycle. A stretch that runs past midnight is joined: end may exceed 96. */
export function busiestWrap(row: number[], thr = 0.5): [number, number] | null {
  const n = row.length;
  const on = row.map((p) => p >= thr);
  if (on.every(Boolean)) return [0, n];
  let start = on.findIndex((v, i) => v && !on[(i - 1 + n) % n]);
  if (start < 0) return null;
  let best: [number, number] | null = null;
  for (let k = 0; k < n; ) {
    const i = (start + k) % n;
    if (on[i]) {
      let len = 0;
      while (len < n && on[(i + len) % n]) len++;
      const s = i;
      if (!best || len > best[1] - best[0]) best = [s, s + len];
      k += len;
    } else k++;
  }
  return best;
}

export function slotLabel(slot: number): string {
  const s = ((slot % 96) + 96) % 96;
  return `${String(Math.floor(s / 4)).padStart(2, "0")}:${String((s % 4) * 15).padStart(2, "0")}`;
}

/** Hours per week likely free: expected away time outside quiet hours, with a rough 95% interval. */
export function idleCapacity(bins: PresenceBin[], quiet: QuietHours): { mean: number; lo: number; hi: number } {
  let sum = 0, varSum = 0;
  for (const b of bins) {
    if (inQuiet(quiet, b.dow, b.slot)) continue;
    sum += (1 - b.p) * 0.25;
    const sd = (b.hi - b.lo) / (2 * 1.96);
    varSum += 0.0625 * sd * sd;
  }
  // Neighbouring bins are correlated, so widen the independent-bin spread.
  const half = 1.96 * Math.sqrt(varSum) * 3.2;
  const r1 = (x: number) => Math.round(x * 10) / 10;
  return { mean: r1(sum), lo: r1(Math.max(0, sum - half)), hi: r1(sum + half) };
}
