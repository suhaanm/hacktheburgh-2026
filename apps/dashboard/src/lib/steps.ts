import { cogLabel, fmtDuration } from "./format";
import type { RibbonColumn } from "./ribbon";

// The words for "My steps against an experienced worker's": the worker's own case lined up with ONE experienced worker's.
// Pure: a number that is not finite is never printed, and an empty ribbon says so in words.

const finite = (n: unknown): n is number => typeof n === "number" && Number.isFinite(n);

/** Seconds lost in the case shown: the engine's own figure for it when it sends one, else the sum over the ribbon's columns. */
export function caseSecondsLost(personGap: unknown, cols: RibbonColumn[]): number {
  if (finite(personGap)) return Math.max(0, personGap);
  return cols.reduce((s, c) => s + (finite(c.lost) ? Math.max(0, c.lost) : 0), 0);
}

/** The columns that lost the most time, biggest first, at most `n`. A column that lost nothing is never listed. */
export function topLosses(cols: RibbonColumn[], n = 4): { cog: string; seconds: number; skipped: boolean }[] {
  return cols
    .filter((c) => finite(c.lost) && c.lost > 0 && (c.expert?.cog || c.novice?.cog))
    .sort((a, b) => b.lost - a.lost)
    .slice(0, n)
    .map((c) => ({ cog: (c.expert?.cog ?? c.novice?.cog) as string, seconds: c.lost, skipped: !c.novice }));
}

/** The one headline sentence for the section. */
export function stepsHeadline(personGap: unknown, cols: RibbonColumn[]): string {
  if (cols.length === 0) return "Your steps appear here once Knack has seen you do this task.";
  const lost = caseSecondsLost(personGap, cols);
  if (lost < 5) return "Your steps matched an experienced worker's on this case, with no time lost.";
  const top = topLosses(cols, 1)[0];
  return `You took ${fmtDuration(lost)} longer than an experienced worker${top ? `, mostly at ${cogLabel(top.cog).toLowerCase()}` : ""}.`;
}
