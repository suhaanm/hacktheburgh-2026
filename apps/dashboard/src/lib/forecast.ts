export interface ForecastPoint {
  d_min: number;
  survival: number;
  lo?: number;
  hi?: number;
}

/** Critical-fractile rule from the spec: start a run of length D only if S(D) > L / (G + L). */
export function threshold(gain: number, loss: number): number {
  return loss / (gain + loss);
}

export function survivalAt(points: ForecastPoint[], d: number): number {
  if (!points.length) return 0;
  if (d <= points[0].d_min) return points[0].survival;
  for (let i = 1; i < points.length; i++) {
    if (d <= points[i].d_min) {
      const a = points[i - 1], b = points[i];
      return a.survival + ((b.survival - a.survival) * (d - a.d_min)) / (b.d_min - a.d_min);
    }
  }
  return points[points.length - 1].survival;
}

export function decideLocal(points: ForecastPoint[], thr: number, d: number): { go: boolean; survival: number } {
  const survival = survivalAt(points, d);
  return { go: survival > thr, survival };
}

/** Longest run length (minutes) that still clears the threshold. */
export function longestWindow(points: ForecastPoint[], thr: number): number {
  let best = 0;
  for (const p of points) if (p.survival > thr) best = Math.max(best, p.d_min);
  // Refine between the last passing point and the next.
  const i = points.findIndex((p) => p.survival <= thr);
  if (i > 0) {
    const a = points[i - 1], b = points[i];
    best = a.d_min + ((a.survival - thr) / (a.survival - b.survival)) * (b.d_min - a.d_min);
  }
  return Math.round(best);
}
