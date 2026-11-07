/** The engine speaks three-letter lowercase day keys ("mon"); the screens use indexes 0 = Monday to 6 = Sunday. */
export const DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;

export function dayIndex(d: string | number): number {
  if (typeof d === "number") return d;
  const i = DAY_KEYS.indexOf(String(d).toLowerCase().slice(0, 3) as (typeof DAY_KEYS)[number]);
  return i;
}

/** Accept either form from a service; return sorted, unique indexes. */
export function normDays(days: readonly (string | number)[] | undefined | null): number[] {
  const set = new Set((days ?? []).map(dayIndex).filter((i) => i >= 0 && i <= 6));
  return [...set].sort((a, b) => a - b);
}

export function dayKeys(idx: readonly number[]): string[] {
  return normDays(idx).map((i) => DAY_KEYS[i]);
}
