// Small guards for text and numbers that come from outside the page (an engine answer, a file, a worker's own words). Pure: no network, no React.
// Used on Needs you, Routines, Your data and Settings so one odd value never breaks a line, a count or a layout (docs/knack-ux/edge-cases-c.md).

/** At most `max` characters, cut on a whole character (never half of an emoji or an accented letter), with an ellipsis. Anything that is not text is "". */
export function clip(value: unknown, max = 120): string {
  const s = typeof value === "string" ? value : typeof value === "number" || typeof value === "boolean" ? String(value) : "";
  const chars = Array.from(s.replace(/\s+/g, " ").trim());
  return chars.length > max ? `${chars.slice(0, Math.max(1, max - 1)).join("").trimEnd()}…` : chars.join("");
}

/** A whole, non-negative count; anything else (negative, NaN, text, missing) is 0. */
export function count(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? Math.max(0, Math.floor(value)) : 0;
}

/** A finite number, or null. Negative numbers are kept: the caller decides whether they make sense. */
export function num(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** An array, or an empty one: a list the engine left out is an empty list, not an error. */
export function arr<T = unknown>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}

/** Only the entries that are real objects, in order, and at most the first of each id (a duplicate id is the same item sent twice). */
export function uniqueBy<T>(rows: unknown, id: (row: T, index: number) => string): T[] {
  const seen = new Set<string>();
  const out: T[] = [];
  arr<T>(rows).forEach((row, i) => {
    if (!row || typeof row !== "object") return;
    const key = id(row, i);
    if (seen.has(key)) return;
    seen.add(key);
    out.push(row);
  });
  return out;
}

/** The time as the engine sent it if it is a real time, else null. A string that is not a date (or a date nobody could have written) is not one. */
export function validTime(iso: unknown): number | null {
  if (typeof iso !== "string" || !iso) return null;
  const t = Date.parse(iso);
  return Number.isNaN(t) ? null : t;
}

/**
 * "13 Nov, 09:20" for a real time; "time unknown" otherwise. A time more than a day ahead of `now` (a clock that is wrong somewhere) is shown as
 * "time unknown" too, rather than as a future date a worker would believe. `now` is a parameter so a test can fix it.
 */
export function whenText(iso: unknown, now: number = Date.now()): string {
  const t = validTime(iso);
  if (t === null || t > now + 24 * 3_600_000) return "time unknown";
  const d = new Date(t);
  return `${d.toLocaleDateString("en-GB", { day: "numeric", month: "short" })}, ${d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}`;
}
