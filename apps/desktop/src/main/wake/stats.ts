// Wilson score interval for a proportion k of n (95% by default). Pure. Used by the offline measurement of the wake phrase matcher.
export interface Proportion {
  k: number
  n: number
  rate: number
  low: number
  high: number
}

export function wilson(k: number, n: number, z = 1.959964): Proportion {
  if (!Number.isInteger(k) || !Number.isInteger(n) || n <= 0 || k < 0 || k > n) throw new Error('wilson: need integers with 0 <= k <= n and n > 0')
  const p = k / n
  const z2 = z * z
  const denom = 1 + z2 / n
  const centre = (p + z2 / (2 * n)) / denom
  const half = (z * Math.sqrt((p * (1 - p)) / n + z2 / (4 * n * n))) / denom
  return { k, n, rate: p, low: Math.max(0, centre - half), high: Math.min(1, centre + half) }
}

export const pct = (x: number, digits = 2): string => `${(x * 100).toFixed(digits)}%`
export const describeProportion = (p: Proportion): string => `${p.k}/${p.n} = ${pct(p.rate)} (95% Wilson ${pct(p.low)} to ${pct(p.high)})`
