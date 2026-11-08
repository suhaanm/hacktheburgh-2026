// The Forecasts screen: up to three plain insights, each with what to expect, what to do about it and one confidence word.
// Pure and total. The model proposes, code decides: every sentence is a fixed template, every figure is read from the answers the Admin routes
// already give (onboarding curves, role comparison, the people list, repeated work), and the confidence word comes from n and the interval.
// Data that is missing, too small, NaN or null never makes a sentence: that insight is left out, or hedged in words ("Too early to say").
import type { FirmWire } from "../repeats/types";
import { hitNumbers, hoursChart, niceTop, onboardingChart, onboardingNumbers, wilson, type ChartRow } from "./charts";
import { capFirst, confidence, confidenceApart, groupName, MIN_N, monthAhead, plural, readableOnboarding, roleWords, shortName, type Confidence } from "./insights";
import { compareShown, fmtShare, trendCounts, TREND_LABEL, unitWord } from "./model";
import type { Est, Trend, WireFirm, WireOnboarding, WireRoles } from "./wire";
import { TRENDS } from "./wire";

export { niceTop, wilson };

export type ForecastKind = "onboarding" | "gap" | "repeated" | "trend";
export type PlotUnit = "share" | "steps" | "hours";

export type ForecastChart =
  | { kind: "interval"; title: string; rows: ChartRow[]; domain: [number, number]; ticks: number[]; unit: PlotUnit }
  | { kind: "mix"; title: string; total: number; parts: { id: Trend; label: string; count: number }[] };

export interface ForecastInsight {
  id: ForecastKind;
  /** A name of two or three words, for the closed rows under "See the numbers". */
  short: string;
  /** What to expect, one sentence. */
  expect: string;
  /** What to do about it, one sentence. */
  todo: string;
  confidence: Confidence;
  /** "n = 8 and 23 people": printed on the card, never behind a hint. */
  n: string;
  /** The size of the effect with its interval, in words, or null when there is no interval. */
  detail: string | null;
  chart: ForecastChart;
  /** The table behind the card: printed under "See the numbers". */
  numbers: { heads: string[]; rows: string[][] };
}

export interface ForecastInput {
  onboarding: WireOnboarding | null;
  roles: WireRoles | null;
  firm: WireFirm | null;
  hits: Pick<FirmWire, "total" | "rows" | "min_group"> | null;
  now: Date;
  min?: number;
}

const fin = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x);
const RANK: Record<Confidence, number> = { likely: 0, possible: 1, too_early: 2 };
const r0 = (x: number): number => Math.round(x);
const f1 = (x: number): string => String(Math.round(x * 10) / 10);

/* -- 1. Onboarding speed ----------------------------------------------------------------------------------------------------- */

function onboardingInsight(i: ForecastInput, min: number): ForecastInsight | null {
  const onb = i.onboarding;
  if (!onb) return null;
  const ok = readableOnboarding(onb.roles, min).sort((a, b) => (a.median_to_target?.value ?? 0) - (b.median_to_target?.value ?? 0));
  if (ok.length < 2) return null;
  const fast = ok[0], slow = ok[ok.length - 1];
  const fm = fast.median_to_target!, sm = slow.median_to_target!;
  const diff = r0(sm.value - fm.value);
  if (diff < 1) return null;
  const unit = unitWord(onb.x_unit);
  const conf = confidenceApart({ n: fast.n, value: fm.value, ci: fm.ci }, { n: slow.n, value: sm.value, ci: sm.ci });
  const month = monthAhead(i.now);
  const newcomers = (i.firm?.roles ?? []).flatMap((r) => r.users).filter((u) => u.role === slow.role && (u.tenure_band === "lt_4w" || u.tenure_band === "1_3m") && !u.time_to_independence.reached).length;
  const slowW = roleWords(slow.name), fastW = roleWords(fast.name);
  const sure = conf !== "too_early";
  const expect = sure
    ? (newcomers > 0 ? `Expect ${plural(newcomers, "new starter")} to need coaching${month ? ` through ${month}` : ""}.` : `Expect new ${slowW} to need coaching for longer.`)
    : `${capFirst(slowW)} may take longer than ${fastW}, but the gap is not clear yet.`;
  const todo = sure ? (newcomers > 0 ? `Start coaching with the newest ${slowW}.` : `Plan extra coaching time for new ${slowW}.`) : "Wait for more people before planning around it.";
  const lo = fm.ci && sm.ci ? r0(Math.min(sm.ci[0] - fm.ci[1], sm.ci[1] - fm.ci[0])) : null;
  const hi = fm.ci && sm.ci ? r0(Math.max(sm.ci[0] - fm.ci[1], sm.ci[1] - fm.ci[0])) : null;
  const ch = onboardingChart(onb, min);
  return {
    id: "onboarding", short: "Onboarding speed", expect, todo, confidence: conf,
    n: `n = ${r0(fast.n)} and ${plural(slow.n, "person", "people")}`,
    detail: lo !== null && hi !== null ? `${capFirst(slowW)} take about ${diff} more ${unit}. Interval ${lo} to ${hi}.` : `Median ${unit === "steps" ? "step" : unit}: ${fastW} ${r0(fm.value)}, ${slowW} ${r0(sm.value)}. One has no interval yet.`,
    chart: { kind: "interval", title: "Median step at which people reach the target, by role", unit: "steps", rows: ch.rows, domain: ch.domain, ticks: ch.ticks },
    numbers: onboardingNumbers(onb, min),
  };
}

/* -- 2. The gap between juniors and experts ---------------------------------------------------------------------------------- */

function gapInsight(i: ForecastInput, min: number): ForecastInsight | null {
  const roles = i.roles;
  if (!roles) return null;
  const rows = roles.roles.flatMap((r) => {
    const m = r.measures.find((x) => x.key === "independence");
    return compareShown(r, min) && m?.gap ? [{ r, m, g: m.gap }] : [];
  }).sort((a, b) => Math.abs(b.g.value) - Math.abs(a.g.value));
  if (rows.length === 0) return null;
  const { r, m, g } = rows[0];
  const n = Math.min(r.n_expert, r.n_junior);
  const conf = m.verdict === "gap" ? confidence({ n, value: g.value, ci: g.ci }) : "too_early";
  const habit = [...r.habits].filter((h) => h.verdict === "gap" && h.explains_s).sort((a, b) => (b.explains_s?.value ?? 0) - (a.explains_s?.value ?? 0))[0]?.label ?? null;
  const pts = Math.abs(r0(g.value * 100));
  const dir = g.value < 0 ? "fewer" : "more";
  const name = groupName(r.name);
  const sure = conf !== "too_early";
  const expect = sure
    ? `Expect junior ${name} to finish ${pts} points ${dir} of their steps without help than experts.`
    : `Junior ${name} may finish ${dir} of their steps without help than experts, but it is not clear yet.`;
  const todo = sure ? (habit ? `Practise “${shortName(habit, 50)}” first.` : "Look at the steps where juniors ask for help most.") : "Wait for more people before acting on it.";
  return {
    id: "gap", short: "Juniors and experts", expect, todo, confidence: conf,
    n: `n = ${plural(r.n_expert, "expert")} and ${plural(r.n_junior, "junior")}`,
    detail: g.ci ? `Gap ${g.value < 0 ? "-" : "+"}${pts} points${habit ? `, mostly on “${shortName(habit, 50)}”` : ""}. Interval ${r0(g.ci[0] * 100)} to ${r0(g.ci[1] * 100)}.` : null,
    chart: {
      kind: "interval", title: `Share of steps finished without help, ${name}`, unit: "share", domain: [0, 1], ticks: [0, 0.25, 0.5, 0.75, 1],
      rows: [
        { id: "expert", label: "Experts", est: m.expert, tone: "expert" },
        { id: "junior", label: "Juniors", est: m.junior, tone: "novice" },
      ],
    },
    numbers: {
      heads: ["Group", "Finished without help (95% interval)", "People"],
      rows: [["Experts", fmtShare(m.expert), String(r.n_expert)], ["Juniors", fmtShare(m.junior), String(r.n_junior)]],
    },
  };
}

/* -- 3. Repeated work -------------------------------------------------------------------------------------------------------- */

function repeatedInsight(i: ForecastInput, min: number): ForecastInsight | null {
  const h = i.hits;
  const total = h?.total?.hours_per_week;
  if (!h || !total || !fin(total.point) || total.point <= 0 || h.rows.length === 0) return null;
  const ch = hoursChart(h.rows, 3);
  if (!ch.any) return null;
  const nums = hitNumbers(h.rows, 30);
  const top = [...h.rows].filter((r) => fin(r.hours_per_week?.point) && r.hours_per_week.point > 0).sort((a, b) => b.hours_per_week.point - a.hours_per_week.point)[0];
  const people = h.total.people;
  const conf = confidence({ n: people, value: total.point, ci: fin(total.lo) && fin(total.hi) ? [total.lo, total.hi] : null, zero: null, min });
  const hours = total.point >= 100 ? r0(total.point).toLocaleString("en-GB") : f1(total.point);
  const sure = conf !== "too_early";
  const expect = sure
    ? `Expect about ${hours} hours a week to free up with routines.`
    : `Repeated work may add up to about ${hours} hours a week.`;
  const todo = sure ? `Offer routines for “${shortName(top.label, 50)}” first.` : "Wait for more people before planning around it.";
  return {
    id: "repeated", short: "Repeated work", expect, todo, confidence: conf,
    n: `n = ${plural(people, "person", "people")}`,
    detail: fin(total.lo) && fin(total.hi) ? `The biggest piece is done by ${top.people.toLocaleString("en-GB")} people. Interval ${f1(total.lo)} to ${f1(total.hi)} hours.` : `The biggest piece is done by ${top.people.toLocaleString("en-GB")} people.`,
    chart: { kind: "interval", title: "Hours a week of repeated work, the three biggest actions", unit: "hours", rows: ch.rows, domain: ch.domain, ticks: ch.ticks },
    numbers: nums,
  };
}

/* -- 4. How the help people need is changing --------------------------------------------------------------------------------- */

function trendInsight(i: ForecastInput, min: number): ForecastInsight | null {
  const all = (i.firm?.roles ?? []).flatMap((r) => r.users);
  if (all.length < min) return null;
  const c = trendCounts(all);
  const total = all.length;
  const talk = c.needs_attention;
  const month = monthAhead(i.now);
  const k = talk > 0 ? talk : c.improving;
  const ci = wilson(k, total);
  const conf = confidence({ n: total, value: k / total, ci, zero: talk > 0 ? 0 : null, min });
  const sure = conf !== "too_early";
  const t = total.toLocaleString("en-GB");
  const expect = talk > 0
    ? (sure ? `Expect ${talk.toLocaleString("en-GB")} of ${t} people to keep needing coaching${month ? ` through ${month}` : ""}.` : `${talk.toLocaleString("en-GB")} of ${t} people may need more coaching; too soon to say.`)
    : `Most people are on track: ${c.improving.toLocaleString("en-GB")} of ${t} need less help.`;
  const todo = talk > 0 ? (sure ? "Offer them a conversation, not a grade." : "Wait for more weeks of data.") : "Keep coaching light; look again next month.";
  return {
    id: "trend", short: "Help over time", expect, todo, confidence: conf,
    n: `n = ${plural(total, "person", "people")}`,
    detail: ci ? `${talk > 0 ? "Their need for help has not fallen as usual" : "Need for help has fallen"}: ${Math.round((k / total) * 100)}% of people. Interval ${Math.round(ci[0] * 100)}% to ${Math.round(ci[1] * 100)}%.` : null,
    chart: { kind: "mix", title: "How the help people need is changing", total, parts: TRENDS.map((x) => ({ id: x, label: TREND_LABEL[x], count: c[x] })) },
    numbers: { heads: ["Trend", "People"], rows: TRENDS.map((x) => [TREND_LABEL[x], String(c[x])]) },
  };
}

/** Up to three insights, the surest first (ties keep this order: onboarding, gap, repeated work, trend). Each builder returns null when its data cannot carry a sentence. */
export function buildForecastInsights(i: ForecastInput): ForecastInsight[] {
  const min = i.min ?? MIN_N;
  const all = [onboardingInsight(i, min), gapInsight(i, min), repeatedInsight(i, min), trendInsight(i, min)].filter((x): x is ForecastInsight => !!x);
  return all.map((x, k) => ({ x, k })).sort((a, b) => RANK[a.x.confidence] - RANK[b.x.confidence] || a.k - b.k).slice(0, 3).map((e) => e.x);
}

export type { Est };
