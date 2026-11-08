// The headline sentence for each Admin screen, and the confidence word. Pure: the words are fixed templates and every figure is read from the data,
// so a model never writes a sentence an admin reads (the model proposes, code decides). Each function is total: empty data, one person, a group under
// the minimum, an interval that spans zero, NaN or null all give a plain sentence, never "NaN" and never a blank. No React here, so it is all tested.
import type { FirmWire } from "../repeats/types";
import { longDate } from "./brief";
import { compareShown, trendCounts, unitWord } from "./model";
import type { Interval, OnboardingRole, WireFirm, WireOnboarding, WireOverview, WireRoles } from "./wire";

/** The smallest group a figure may describe (the privacy threshold used across the Firm screens). */
export const MIN_N = 5;

const fin = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x);
const okInterval = (ci: Interval | null | undefined): ci is Interval => !!ci && fin(ci[0]) && fin(ci[1]) && ci[0] <= ci[1];

/* -- Words ------------------------------------------------------------------------------------------------------------------- */

/** "3 people", "1 person", "0 approvals". Counts that are not finite or negative read as zero. */
export function plural(n: number, one: string, many = `${one}s`): string {
  const k = fin(n) && n > 0 ? Math.round(n) : 0;
  return `${k.toLocaleString("en-GB")} ${k === 1 ? one : many}`;
}

/** A name kept to a length a sentence can carry. A very long role or person name is cut with an ellipsis, never allowed to break the line. */
/** "Data analyst" as a group of people: "data analysts". Lower case unless the word is an acronym (UK), an s on the last word. */
export function groupName(name: string | null | undefined): string {
  const s = shortName(name, 40);
  if (s === "this role") return "people in this role";
  const words = s.split(" ").map((w, i) => (i === 0 && !/^[A-Z]{2,}$/.test(w) ? w.toLowerCase() : w));
  const last = words.length - 1;
  if (!/s$/i.test(words[last])) words[last] = `${words[last]}s`;
  return words.join(" ");
}

export function shortName(name: string | null | undefined, max = 32): string {
  const s = (name ?? "").replace(/\s+/g, " ").trim();
  if (!s) return "this role";
  const chars = [...s];
  if (chars.length <= max) return s;
  // Cut at a word boundary when one is near enough, so a long label does not end mid-word.
  const cut = chars.slice(0, max - 1).join("");
  const space = cut.lastIndexOf(" ");
  return `${(space >= max * 0.6 ? cut.slice(0, space) : cut).trimEnd()}…`;
}

/** "Programmer" -> "programmers"; "Benefits processors" stays; an acronym keeps its capitals ("QA" -> "QAs"). */
export function roleWords(name: string | null | undefined, max = 32): string {
  if (!(name ?? "").trim()) return "people in this role";
  const s = shortName(name, max);
  const lower = /^[A-Z][a-z]/.test(s) ? `${s[0].toLowerCase()}${s.slice(1)}` : s;
  // Only a name that ends in a Latin letter takes an "s": a name in another script, or one ending in a symbol, is left as it is.
  return /[A-Za-z]$/.test(lower) && !/s$/i.test(lower) ? `${lower}s` : lower;
}
export const capFirst = (s: string): string => (s ? `${s[0].toUpperCase()}${s.slice(1)}` : s);

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
/** The month name of a date a few weeks ahead, or null when the clock gave nothing usable. */
export function monthAhead(now: Date, days = 28): string | null {
  const t = now.getTime();
  if (!fin(t)) return null;
  const d = new Date(t + days * 86_400_000);
  return MONTHS[d.getUTCMonth()] ?? null;
}

/* -- Confidence -------------------------------------------------------------------------------------------------------------- */

export type Confidence = "likely" | "possible" | "too_early";
export const CONFIDENCE_WORD: Record<Confidence, string> = { likely: "Likely", possible: "Possible", too_early: "Too early to say" };
export const CONFIDENCE_HINT: Record<Confidence, string> = {
  likely: "The interval clears zero and at least ten people stand behind it.",
  possible: "The interval clears zero, but fewer than ten people stand behind it, or the interval is wide.",
  too_early: "Fewer than five people, no interval, or an interval that includes no change. Not the same as no change.",
};

/**
 * One word for how far the data supports a forecast, chosen by code from n and the interval (never by a model).
 * `zero` is the value that means "no change" (0 for a difference); pass null for a plain amount, where only n and the width count.
 */
export function confidence(a: { n: number | null | undefined; value: number | null | undefined; ci: Interval | null | undefined; zero?: number | null; min?: number }): Confidence {
  const min = a.min ?? MIN_N;
  const zero = a.zero === undefined ? 0 : a.zero;
  if (!fin(a.n) || a.n < min) return "too_early";
  if (!fin(a.value) || !okInterval(a.ci)) return "too_early";
  if (zero !== null && a.ci[0] <= zero && a.ci[1] >= zero) return "too_early";
  const wide = a.value !== 0 && (a.ci[1] - a.ci[0]) / Math.abs(a.value) > 1.5;
  return a.n >= 2 * min && !wide ? "likely" : "possible";
}

/** Two independent estimates: their difference is readable only when the two intervals do not overlap. */
export function confidenceApart(a: { n: number; value: number; ci: Interval | null }, b: { n: number; value: number; ci: Interval | null }): Confidence {
  if (!okInterval(a.ci) || !okInterval(b.ci)) return "too_early";
  const apart = a.ci[1] < b.ci[0] || b.ci[1] < a.ci[0];
  const n = Math.min(a.n, b.n);
  if (!apart) return "too_early";
  return confidence({ n, value: a.value - b.value, ci: [Math.min(a.ci[0] - b.ci[1], a.ci[1] - b.ci[0]), Math.max(a.ci[0] - b.ci[1], a.ci[1] - b.ci[0])], zero: 0 });
}

/* -- Freshness: numbers that are old, or dated after today --------------------------------------------------------------------- */

export type Freshness = { state: "fresh" | "stale" | "future" | "unknown"; days: number | null; text: string | null };
/** `asOf` is the date the numbers were worked out. More than 14 days old, or dated after today, is said in words. An unreadable date says nothing. */
export function freshness(asOf: string | null | undefined, now: Date): Freshness {
  const t = asOf ? Date.parse(asOf) : NaN;
  const n = now.getTime();
  if (!fin(t) || !fin(n)) return { state: "unknown", days: null, text: null };
  const days = Math.floor((n - t) / 86_400_000);
  const date = longDate(asOf);
  if (days < -1) return { state: "future", days, text: `These numbers are dated ${date ?? "after today"}, which is after today. Check the clock.` };
  if (days > 14) return { state: "stale", days, text: `These numbers are from ${date ?? "a while ago"}, ${days >= 365 ? `${Math.floor(days / 365)} ${Math.floor(days / 365) === 1 ? "year" : "years"}` : days >= 60 ? `${Math.floor(days / 30)} months` : `${days} days`} ago.` };
  return { state: "fresh", days, text: null };
}

/* -- Headlines --------------------------------------------------------------------------------------------------------------- */

/** Firm overview: how many things need a look this week, and how many people the firm has. */
export function firmHeadline(o: WireOverview): string {
  const people = o.firm.users;
  const roles = o.firm.roles;
  const where = people > 0 ? ` across ${plural(people, "person", "people")} in ${plural(roles, "role")}` : "";
  if (people <= 0 && o.top.length === 0) return "No one is in the firm view yet.";
  const attention = o.top.filter((i) => i.polarity === "attention").length;
  if (o.top.length === 0) return `Nothing stands out this week${where}.`;
  if (attention === 0) return `Nothing needs attention this week${where}.`;
  // The list under the headline holds every finding, the good ones too: the two numbers must agree with it.
  if (attention < o.top.length) return `${plural(o.top.length, "thing")} this week, ${attention} of them ${attention === 1 ? "needs" : "need"} a look${where}.`;
  return `${plural(attention, "thing")} ${attention === 1 ? "needs" : "need"} a look this week${where}.`;
}

/** The widest readable gap between juniors and experts, or why none is. Gaps are read from the independence measure, in points of steps finished without help. */
export function rolesHeadline(roles: WireRoles, min = MIN_N): string {
  if (roles.roles.length === 0) return "No roles to compare yet.";
  const compared = roles.roles.filter((r) => compareShown(r, min));
  if (compared.length === 0) return `No role has ${min} experts and ${min} juniors yet, so none is compared.`;
  const gaps = compared.flatMap((r) => {
    const m = r.measures.find((x) => x.key === "independence");
    return m?.gap && m.verdict === "gap" ? [{ r, g: m.gap.value }] : [];
  });
  if (gaps.length === 0) return "No gap between juniors and experts can be read yet.";
  gaps.sort((a, b) => Math.abs(b.g) - Math.abs(a.g));
  const top = gaps[0];
  const pts = Math.abs(Math.round(top.g * 100));
  const dir = top.g < 0 ? "fewer" : "more";
  const base = `Junior ${groupName(top.r.name)} finish ${pts} points ${dir} of their steps without help than experts`;
  return gaps.length > 1 ? `${base}, the widest gap across ${gaps.length} roles.` : `${base}.`;
}

/** How the help people need is changing: how many need less, how many could use a conversation. */
export function peopleHeadline(firm: WireFirm): string {
  const all = firm.roles.flatMap((r) => r.users);
  if (all.length === 0) return "No one is listed yet.";
  const c = trendCounts(all);
  const total = all.length;
  const better = c.improving;
  const talk = c.needs_attention;
  if (better === 0 && talk === 0) return total < MIN_N ? `Only ${plural(total, "person", "people")} so far, too few for a trend.` : `No one has a clear trend yet among ${plural(total, "person", "people")}.`;
  const first = better > 0 ? `${better.toLocaleString("en-GB")} of ${total.toLocaleString("en-GB")} people need less help than before` : `${plural(total, "person", "people")} so far, none with a falling need for help`;
  return talk > 0 ? `${first}; ${talk.toLocaleString("en-GB")} could use a conversation.` : `${first}.`;
}

/** Roles whose onboarding median can be read: n at least the minimum, a median, no reason to leave it out. */
export function readableOnboarding(roles: OnboardingRole[], min = MIN_N): OnboardingRole[] {
  return roles.filter((r) => !r.reason && r.n >= min && !!r.median_to_target && fin(r.median_to_target.value));
}

export function onboardingHeadline(data: WireOnboarding, min = MIN_N): string {
  if (data.roles.length === 0) return "No one has been followed through onboarding yet.";
  const ok = readableOnboarding(data.roles, min).sort((a, b) => (a.median_to_target?.value ?? 0) - (b.median_to_target?.value ?? 0));
  const unit = unitWord(data.x_unit);
  if (ok.length === 0) return `Fewer than ${min} people have been followed in any role, so no onboarding speed is shown.`;
  if (ok.length === 1) return `Half of ${roleWords(ok[0].name)} reach the target by ${unit === "steps" ? "step" : unit} ${Math.round(ok[0].median_to_target?.value ?? 0)}.`;
  const fast = ok[0];
  const slow = ok[ok.length - 1];
  const fm = fast.median_to_target!, sm = slow.median_to_target!;
  const diff = Math.round(sm.value - fm.value);
  if (diff < 1) return `All ${plural(ok.length, "role")} reach the target at about the same point.`;
  // A difference is stated only when the two intervals do not overlap; otherwise the sentence says the gap is not clear.
  if (confidenceApart({ n: fast.n, value: fm.value, ci: fm.ci }, { n: slow.n, value: sm.value, ci: sm.ci }) === "too_early") {
    return `${capFirst(roleWords(fast.name))} may reach the target sooner than ${roleWords(slow.name)}, but the gap is not clear yet.`;
  }
  return `${capFirst(roleWords(fast.name))} reach the target about ${diff} ${unit} sooner than ${roleWords(slow.name)}.`;
}

/** Repeated work: hours a week across the firm and the biggest single piece. */
export function automationHeadline(d: Pick<FirmWire, "total" | "rows">): string {
  const h = d.total?.hours_per_week?.point;
  const people = d.total?.people ?? 0;
  if (!fin(h) || h <= 0 || d.rows.length === 0) return `No repeated work stands out across ${plural(people, "person", "people")} yet.`;
  const top = [...d.rows].sort((a, b) => (fin(b.hours_per_week?.point) ? b.hours_per_week.point : 0) - (fin(a.hours_per_week?.point) ? a.hours_per_week.point : 0))[0];
  const hours = h >= 100 ? Math.round(h).toLocaleString("en-GB") : String(Math.round(h * 10) / 10);
  const label = top?.label ? `, the biggest piece being “${shortName(top.label, 50)}”` : "";
  return `About ${hours} hours a week of repeated work across ${plural(people, "person", "people")}${label}.`;
}

/** Risk: approvals waiting, runs paused, everything stopped. Quiet when there is nothing. */
export function riskHeadline(o: WireOverview): string {
  const r = o.risk;
  if (!r) return "No risk figures have been sent yet.";
  const parts: { long: string; short: string }[] = [];
  if (r.open_approvals > 0) {
    const age = r.approval_backlog_age_h && fin(r.approval_backlog_age_h.max) ? `, the oldest for ${Math.round(r.approval_backlog_age_h.max)} hours` : "";
    parts.push({ long: `${plural(r.open_approvals, "approval")} ${r.open_approvals === 1 ? "is" : "are"} waiting${age}`, short: plural(r.open_approvals, "waiting approval") });
  }
  if (r.injection_pauses_30d > 0) parts.push({ long: `${plural(r.injection_pauses_30d, "run")} ${r.injection_pauses_30d === 1 ? "was" : "were"} paused after a page tried to instruct ${r.injection_pauses_30d === 1 ? "it" : "them"}`, short: plural(r.injection_pauses_30d, "paused run") });
  if (r.kill_events_30d > 0) parts.push({ long: `everything was stopped ${plural(r.kill_events_30d, "time")}`, short: plural(r.kill_events_30d, "full stop") });
  if (parts.length === 0) return "Nothing is waiting and nothing was stopped in the last 30 days.";
  // One sentence: the first thing in full, then the others by name. The figures are one line each under it.
  const rest = parts.slice(1).map((p) => p.short);
  return `${capFirst(parts[0].long)}${rest.length > 0 ? `; also ${rest.length > 1 ? `${rest.slice(0, -1).join(", ")} and ${rest[rest.length - 1]}` : rest[0]}` : ""}.`;
}

/** The firm brief's first line: how many people, how many roles, how many have enough data for a trend. */
export function briefHeadline(o: WireOverview): string {
  const u = o.firm.users;
  if (u <= 0) return "There is no one in the firm brief yet.";
  return `${plural(u, "person", "people")} in ${plural(o.firm.roles, "role")}; ${o.coverage.enough_data.toLocaleString("en-GB")} ${o.coverage.enough_data === 1 ? "has" : "have"} enough data for a trend.`;
}

