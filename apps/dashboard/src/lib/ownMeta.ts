import type { AnalyticMeta } from "../types";

// A worker's screen draws the worker's own data and ONE experienced worker's: it never prints how many other people a figure came from
// (docs/knack-ux/views.md). The engine's answer carries the n of the group it was computed over ("24 people"); this swaps it for what the
// screen really draws (one case, one week) and drops a split that is about people. A unit that is not about people passes through unchanged.

const PEOPLE = /\b(?:people|persons?|learners?|workers?|users?|colleagues?|experts?|novices?|participants?|apprentices?|personas?|members?|teammates?|staff)\b/i;

export const aboutPeople = (unit: string | null | undefined): boolean => PEOPLE.test(unit ?? "");

export function ownMeta(m: AnalyticMeta | null, own: { n: number; unit: string }): AnalyticMeta | null {
  if (!m) return null;
  // The engine's note says how the group was made ("4 novices, 9 episodes each", "the mean over all novice cases"): a worker's screen does not print it.
  const note = m.note && aboutPeople(m.note) ? null : m.note;
  if (!aboutPeople(m.n_unit)) return note !== m.note || (m.split && aboutPeople(m.split)) ? { ...m, note, split: m.split && aboutPeople(m.split) ? null : m.split } : m;
  return { ...m, n: own.n, n_unit: own.n === 1 ? own.unit : `${own.unit}s`, split: null, note };
}
