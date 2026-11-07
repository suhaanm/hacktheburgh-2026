import type { Est, FirmRow, HitRow, Stops } from "./types";

/** Minutes a week as a person would say it: "56 min", or "1.5 h" once it passes 100 minutes. Always with its unit. */
export function fmtMinutes(m: number): string {
  if (m >= 100) return `${trim(m / 60, 1)} h`;
  return `${Math.max(0, Math.round(m))} min`;
}

/** Hours a week: "53 h", "0.8 h". */
export function fmtHours(h: number): string {
  return `${trim(h, h >= 10 ? 0 : h >= 1 ? 1 : 2)} h`;
}

function trim(n: number, digits: number): string {
  const s = n.toFixed(digits);
  return digits > 0 ? s.replace(/\.?0+$/, "") : s;
}

/** "32 to 87 min" in the unit the point estimate uses, so the two always read together. */
export function fmtRange(e: Est): string {
  if (e.point >= 100) return `${trim(e.lo / 60, 1)} to ${trim(e.hi / 60, 1)} h`;
  return `${Math.round(e.lo)} to ${Math.round(e.hi)} min`;
}

export function fmtHoursRange(e: Est): string {
  const d = e.point >= 10 ? 0 : e.point >= 1 ? 1 : 2;
  return `${trim(e.lo, d)} to ${trim(e.hi, d)} h`;
}

/** `label` split around the bold key, case-insensitively, first match. No key or no match: the whole label is plain. */
export function splitKey(label: string, key: string | null): [string, string, string] {
  if (!key) return [label, "", ""];
  const i = label.toLowerCase().indexOf(key.toLowerCase());
  if (i < 0) return [label, "", ""];
  return [label.slice(0, i), label.slice(i, i + key.length), label.slice(i + key.length)];
}

export const timesText = (n: number): string => `${n.toLocaleString("en-GB")} ${n === 1 ? "time" : "times"}`;
export const peopleText = (n: number): string => `${n.toLocaleString("en-GB")} ${n === 1 ? "person" : "people"}`;

/** What the automation would stop before, as a plain phrase for "It stops before ...". */
export const STOPS_TEXT: Record<Stops, string> = {
  none: "nothing: none of its steps is hard to undo",
  submit: "submitting or closing a case",
  payment: "issuing or approving a payment",
  message: "sending a letter or a message",
  delete: "deleting or overwriting a record",
  share: "sharing, exporting or publishing",
  release: "merging or deploying",
};

export const STATUS_TEXT: Record<string, string> = { proposed: "proposed", learning: "learning", running: "running", automated: "automated" };

export function rowSummary(r: HitRow): string {
  return `${r.label}, ${timesText(r.count)}, could save about ${fmtMinutes(r.minutes_per_week.point)} a week`;
}

export function firmSummary(r: FirmRow): string {
  return `${r.label}, ${peopleText(r.people)}, about ${fmtHours(r.hours_per_week.point)} a week`;
}

/** The first `limit` rows unless the worker asked for all of them. */
export function shownRows<T>(rows: T[], showAll: boolean, limit: number): T[] {
  return showAll || rows.length <= limit ? rows : rows.slice(0, limit);
}

/** Arrow keys move between rows; Home and End jump. Returns the new index, or null when the key is not one of ours. */
export function moveIndex(i: number, key: string, n: number): number | null {
  if (n <= 0) return null;
  if (key === "ArrowDown") return Math.min(n - 1, i + 1);
  if (key === "ArrowUp") return Math.max(0, i - 1);
  if (key === "Home") return 0;
  if (key === "End") return n - 1;
  return null;
}

/** "56 min" for one row's tooltip-free explanation: the figures behind the number, in plain words. */
export function minutesExplained(r: HitRow, windowDays: number): string {
  const per = r.seconds_per_time >= 90 ? `${trim(r.seconds_per_time / 60, 1)} min` : `${Math.round(r.seconds_per_time)} s`;
  const j = Math.round(r.judgement_share * 100);
  return `About ${fmtMinutes(r.minutes_per_week.point)} a week, between ${fmtRange(r.minutes_per_week)} (95% interval). ` +
    `${timesText(r.count)} in ${windowDays} days at about ${per} each` + (j > 0 ? `, of which ${j}% is judgement you would still do.` : ".");
}

/** The sentence under the page title. */
export function ledeFor(actions: number, hours: Est, windowDays: number): string {
  const n = actions === 1 ? "One thing" : `${actions} things`;
  return `${n} you did by hand in the last ${windowDays} days, about ${fmtHours(hours.point)} a week.`;
}

const HELD: Record<string, [string, string]> = {
  irreversible_first_step: ["begins with a step that cannot be undone", "begin with a step that cannot be undone"],
  judgement: ["needs your judgement", "need your judgement"],
  unstable: ["varies too much from one time to the next", "vary too much from one time to the next"],
  denylist: ["involves something on your denylist", "involve something on your denylist"],
};

/** One quiet line for what repeats but is not offered, and for rows cut by the ten row limit. Empty when there is nothing to say. */
export function heldText(held: { reason: string; count: number }[], notShown: number): string {
  const parts = held.filter((h) => h.count > 0 && HELD[h.reason]).map((h) => `${h.count} ${HELD[h.reason][h.count === 1 ? 0 : 1]}`);
  const total = held.reduce((a, h) => a + (HELD[h.reason] ? h.count : 0), 0);
  const first = total ? `${total} more ${total === 1 ? "repeats but is" : "repeat but are"} not offered: ${parts.join(", ")}.` : "";
  const second = notShown > 0 ? `${notShown} smaller ${notShown === 1 ? "one is" : "ones are"} not shown.` : "";
  return [first, second].filter(Boolean).join(" ");
}

/** The figures behind the sentence under the title. */
export function totalExplained(repeats: number, episodes: number, hours: Est, windowDays: number): string {
  return `About ${fmtHours(hours.point)} a week, between ${fmtHoursRange(hours)} (95% interval), from ${repeats.toLocaleString("en-GB")} repeats in ${episodes.toLocaleString("en-GB")} cases over ${windowDays} days.`;
}

/** "coach first: ENTER_HOUSEHOLD at L1. ..." as a sentence; anything else as the engine wrote it. */
export function plainGate(message: string): string {
  const m = /coach first:\s*([A-Z_]+)\s+at\s+L(\d)/i.exec(message);
  return m ? `Your skill at ${m[1].toLowerCase().replace(/_/g, " ")} is at level ${m[2]}. Automating starts at level 4.` : message;
}
