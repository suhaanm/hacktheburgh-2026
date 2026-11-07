/** Wilson score lower bound for a success rate, z = 1.96 (95%). Spec 7.1 `trust/`. */
export function wilsonLower(successes: number, n: number, z = 1.96): number {
  if (n <= 0) return 0;
  const p = successes / n;
  const z2 = z * z;
  const centre = p + z2 / (2 * n);
  const margin = z * Math.sqrt((p * (1 - p)) / n + z2 / (4 * n * n));
  return Math.max(0, (centre - margin) / (1 + z2 / n));
}

export interface RungInfo {
  id: "A0" | "A1" | "A2" | "A3";
  name: string;
  does: string;
  /** Wilson lower bound needed to reach this rung, null when none. */
  bound: number | null;
  /** Minimum shadow runs, null when none. */
  runs: number | null;
}

/** Ladder from spec 7.1: A0 observe, A1 suggest and shadow, A2 do with approval, A3 do then report. */
export const RUNGS: RungInfo[] = [
  { id: "A0", name: "Observe", does: "Watches and suggests. Does nothing for you.", bound: null, runs: null },
  { id: "A1", name: "Shadow", does: "Practises on your next cases without saving. You compare.", bound: null, runs: null },
  { id: "A2", name: "With approval", does: "Does the work in the background and asks before outward steps.", bound: 0.8, runs: 20 },
  { id: "A3", name: "Then report", does: "Does the work, then tells you. A target the demo does not reach.", bound: 0.95, runs: 75 },
];

export function nextRung(id: RungInfo["id"]): RungInfo | null {
  const i = RUNGS.findIndex((r) => r.id === id);
  return i >= 0 && i < RUNGS.length - 1 ? RUNGS[i + 1] : null;
}

/** How many more clean runs (no failures from here on) are needed to reach a bound. */
export function cleanRunsNeeded(successes: number, n: number, bound: number, cap = 400): number | null {
  for (let extra = 0; extra <= cap; extra++) {
    if (wilsonLower(successes + extra, n + extra) >= bound) return extra;
  }
  return null;
}
