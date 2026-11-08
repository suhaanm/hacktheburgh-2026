import type { AlignCol, CogSegment, Genome } from "../types";

export interface RibbonBlock {
  cog: string;
  x: number;
  w: number;
  seconds: number;
}

export interface RibbonColumn {
  index: number;
  x: number;
  w: number;
  op: AlignCol["op"];
  expert: RibbonBlock | null;
  novice: RibbonBlock | null;
  /** Seconds lost, taken straight from the alignment. */
  lost: number;
  /** Seconds saved: the alignment gave a negative number (a skipped step shows as time saved). */
  saved: number;
  /** Which lane has the hole: the step is missing for that person. */
  missing: "expert" | "novice" | null;
}

export interface RibbonLayout {
  columns: RibbonColumn[];
  width: number;
  totalLost: number;
  totalSaved: number;
  maxLost: number;
  expertTotal: number;
  noviceTotal: number;
}

const dwell = (s: CogSegment | undefined) => (s ? Math.max(0, s.t1 - s.t0) : 0);

/**
 * Column width is proportional to the longer of the two durations in that column, with a floor so
 * short steps stay readable. Within a column each block is that person's duration as a share of the
 * column. Gaps are decided by the alignment indices (a null index means that person has no step
 * there), not by the op name.
 */
export function layoutRibbon(genome: Genome, width: number, gap = 3, minCol = 30): RibbonLayout {
  const { alignment, expert, novice } = genome;
  const cols = alignment.map((a) => {
    const e = a.i != null ? expert.segments[a.i] : undefined;
    const n = a.j != null ? novice.segments[a.j] : undefined;
    return { a, e, n, span: Math.max(dwell(e), dwell(n), 1) };
  });
  const gaps = gap * Math.max(0, cols.length - 1);
  // Find a scale so that the floored widths still add up to `width`.
  let scale = (width - gaps) / cols.reduce((s, c) => s + c.span, 0);
  for (let k = 0; k < 6; k++) {
    const fixed = cols.filter((c) => c.span * scale < minCol);
    const free = cols.filter((c) => c.span * scale >= minCol);
    const freeSpan = free.reduce((s, c) => s + c.span, 0);
    if (!fixed.length || !freeSpan) break;
    scale = (width - gaps - fixed.length * minCol) / freeSpan;
  }
  let x = 0;
  const columns: RibbonColumn[] = cols.map((c, index) => {
    const w = Math.max(minCol, c.span * scale);
    const col: RibbonColumn = {
      index,
      x,
      w,
      op: c.a.op,
      expert: c.e ? { cog: c.e.cog, x, w: (dwell(c.e) / c.span) * w, seconds: dwell(c.e) } : null,
      novice: c.n ? { cog: c.n.cog, x, w: (dwell(c.n) / c.span) * w, seconds: dwell(c.n) } : null,
      lost: Math.max(0, c.a.seconds),
      saved: Math.max(0, -c.a.seconds),
      missing: !c.e && c.n ? "expert" : c.e && !c.n ? "novice" : null,
    };
    x += w + gap;
    return col;
  });
  const totalLost = columns.reduce((s, c) => s + c.lost, 0);
  const totalSaved = columns.reduce((s, c) => s + c.saved, 0);
  return {
    columns,
    width: Math.max(0, x - gap),
    totalLost,
    totalSaved,
    maxLost: Math.max(0, ...columns.map((c) => c.lost)),
    expertTotal: expert.segments.reduce((s, g) => s + dwell(g), 0),
    noviceTotal: novice.segments.reduce((s, g) => s + dwell(g), 0),
  };
}

/** Trapezoid joining a matched expert block to its novice block, as an SVG path. */
export function connectorPath(col: RibbonColumn, yTop: number, yBottom: number): string | null {
  if (!col.expert || !col.novice) return null;
  const e = col.expert, n = col.novice;
  const mid = (yTop + yBottom) / 2;
  return `M${e.x},${yTop} L${e.x + e.w},${yTop} C${e.x + e.w},${mid} ${n.x + n.w},${mid} ${n.x + n.w},${yBottom} L${n.x},${yBottom} C${n.x},${mid} ${e.x},${mid} ${e.x},${yTop} Z`;
}

export function columnCaption(col: RibbonColumn): string {
  const e = col.expert ? `${col.expert.cog.toLowerCase().replace(/_/g, " ")} ${Math.round(col.expert.seconds)} s` : "no step";
  const n = col.novice ? `${col.novice.cog.toLowerCase().replace(/_/g, " ")} ${Math.round(col.novice.seconds)} s` : "no step";
  return `Expert: ${e}. Novice: ${n}. Lost: ${Math.round(col.lost)} s.`;
}

const cogText = (c: string) => c.toLowerCase().replace(/_/g, " ");

/** Who "expert" and "novice" are in a sentence: the group's words, or the worker's own ("you") against one experienced worker. */
export type Voice = "group" | "you";

/** One plain sentence for a column, used by the scrubber and as the accessible name of the column. */
export function describeColumn(col: RibbonColumn, index: number, total: number, voice: Voice = "group"): string {
  const you = voice === "you";
  const E = you ? "The experienced worker" : "Expert";
  const e = you ? "the experienced worker" : "the expert";
  const pos = `Step ${index + 1} of ${total}. `;
  const lost = Math.round(col.lost);
  if (col.expert && col.novice) {
    const same = col.expert.cog === col.novice.cog;
    const what = same
      ? (you ? `Both of you did ${cogText(col.expert.cog)}.` : `Both did ${cogText(col.expert.cog)}.`)
      : (you ? `${E} did ${cogText(col.expert.cog)}, you did ${cogText(col.novice.cog)}.` : `Expert did ${cogText(col.expert.cog)}, novice did ${cogText(col.novice.cog)}.`);
    const times = you ? `${E} ${Math.round(col.expert.seconds)} s, you ${Math.round(col.novice.seconds)} s.` : `Expert ${Math.round(col.expert.seconds)} s, novice ${Math.round(col.novice.seconds)} s.`;
    return `${pos}${what} ${times} ${lost > 0 ? `${lost} s lost.` : "No time lost."}`;
  }
  if (col.novice) return `${pos}${you ? "Only you did this" : "Only the novice did this"}: ${cogText(col.novice.cog)}, ${Math.round(col.novice.seconds)} s. ${lost} s lost.`;
  if (col.expert) {
    const saved = Math.round(col.saved);
    const price = saved > 0 ? `Skipping it shows as ${saved} s saved here, but it often costs more later.` : `${lost} s counted as lost.`;
    return `${pos}Only ${e} did this: ${cogText(col.expert.cog)}, ${Math.round(col.expert.seconds)} s. ${you ? "You" : "The novice"} skipped it. ${price}`;
  }
  return pos;
}
