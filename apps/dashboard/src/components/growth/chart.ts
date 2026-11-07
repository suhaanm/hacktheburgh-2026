// Pure helpers for the Growth chart: scales, ticks and nearest-point lookup. Kept apart from React so they can be tested.
import { scaleLinear } from "d3-scale";

export interface Frame {
  width: number;
  compact: boolean;
  left: number;
  right: number;
  top: number;
  plotH: number;
}

export function frameFor(width: number): Frame {
  const compact = width < 560;
  return { width, compact, left: compact ? 36 : 44, right: compact ? 36 : 52, top: 12, plotH: compact ? 190 : 240 };
}

/** Occurrence axis: 0 to the last occurrence shown. */
export function xScale(maxI: number, f: Frame) {
  return scaleLinear().domain([0, Math.max(1, maxI)]).range([f.left, Math.max(f.left + 40, f.width - f.right)]);
}

/** Share axis: always 0 to 100%, so the curve is read on one scale whatever the data. */
export function yScale(f: Frame) {
  return scaleLinear().domain([0, 1]).range([f.top + f.plotH, f.top]);
}

export const Y_TICKS = [0, 0.25, 0.5, 0.75, 1];

/** Round-number ticks along the occurrence axis, never past the last occurrence. */
export function xTicks(maxI: number, count: number): number[] {
  return scaleLinear().domain([0, Math.max(1, maxI)]).ticks(count).filter((t) => t <= maxI);
}

/** Index of the value in `xs` (ascending) closest to `x`. */
export function nearestIndex(xs: number[], x: number): number {
  if (!xs.length) return -1;
  let lo = 0, hi = xs.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (xs[mid] < x) lo = mid + 1; else hi = mid;
  }
  return lo > 0 && Math.abs(xs[lo - 1] - x) <= Math.abs(xs[lo] - x) ? lo - 1 : lo;
}
