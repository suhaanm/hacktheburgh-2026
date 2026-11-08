// What each Admin chart draws, as plain data: rows with their intervals, a round axis, and the table that sits behind the chart.
// Pure and total, shared by the Forecasts cards and the screens, so a chart and its sentence always read the same numbers.
import type { FirmRow } from "../repeats/types";
import { MIN_N, readableOnboarding, shortName } from "./insights";
import { compareShown, fmtShare, unitWord } from "./model";
import type { Est, OnboardingRole, WireOnboarding, WireRoles } from "./wire";

const fin = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x);
const r0 = (x: number): number => Math.round(x);

export interface ChartRow { id: string; label: string; est: Est | null; tone: "expert" | "novice" | "neutral"; hollow?: boolean }
export interface ChartData { rows: ChartRow[]; domain: [number, number]; ticks: number[] }

/** A round top and a few ticks for a 0-based axis. Never below 1, never NaN. */
export function niceTop(max: number, steps = 4): { top: number; ticks: number[] } {
  const m = fin(max) && max > 0 ? max : 1;
  const raw = m / steps;
  const pow = 10 ** Math.floor(Math.log10(raw));
  const unit = [1, 2, 2.5, 5, 10].map((k) => k * pow).find((u) => u >= raw) ?? raw;
  const top = unit * steps;
  return { top, ticks: Array.from({ length: steps + 1 }, (_, i) => Math.round(i * unit * 100) / 100) };
}

/** 95% Wilson interval for k of n (the normal approximation misbehaves for small counts). Null when the counts make no sense. */
export function wilson(k: number, n: number): [number, number] | null {
  if (!fin(k) || !fin(n) || n <= 0 || k < 0 || k > n) return null;
  const z = 1.96, p = k / n, z2 = z * z;
  const c = (p + z2 / (2 * n)) / (1 + z2 / n);
  const h = (z * Math.sqrt((p * (1 - p)) / n + z2 / (4 * n * n))) / (1 + z2 / n);
  return [Math.max(0, c - h), Math.min(1, c + h)];
}

/** An axis that holds zero and every point and interval end, on steps of 5, 10, 20 or 50 points, never fewer than two steps wide. */
export function pointsAxis(values: number[]): { domain: [number, number]; ticks: number[] } {
  const v = values.filter(fin);
  const lo = Math.min(0, ...v), hi = Math.max(0, ...v);
  const span = Math.max(hi - lo, 10);
  const step = [5, 10, 20, 50, 100].find((s) => span / s <= 5) ?? 100;
  const a = Math.floor(lo / step) * step, b = Math.max(Math.ceil(hi / step) * step, a + 2 * step);
  const ticks: number[] = [];
  for (let t = a; t <= b + 1e-9; t += step) ticks.push(t);
  return { domain: [a, b], ticks };
}

/** The gap between juniors and experts in points of steps finished without help, one row per role that can be compared. Hollow when the interval spans zero. */
export function gapChart(roles: WireRoles, min = MIN_N): (ChartData & { any: boolean }) {
  const rows: ChartRow[] = roles.roles.flatMap((r) => {
    const m = r.measures.find((x) => x.key === "independence");
    if (!compareShown(r, min) || !m?.gap) return [];
    const g = m.gap;
    const est: Est = { value: g.value * 100, ci: g.ci ? [g.ci[0] * 100, g.ci[1] * 100] : null };
    return [{ id: r.role, label: shortName(r.name, 22), est, tone: "neutral" as const, hollow: m.verdict !== "gap" }];
  });
  const axis = pointsAxis(rows.flatMap((r) => (r.est ? [r.est.value, ...(r.est.ci ?? [])] : [])));
  return { rows, any: rows.length > 0, ...axis };
}

/** The median step at which each readable role reaches the target, with its interval, on one 0-based axis. */
export function onboardingChart(data: WireOnboarding, min = MIN_N): (ChartData & { any: boolean }) {
  const ok = readableOnboarding(data.roles, min).sort((a, b) => (a.median_to_target?.value ?? 0) - (b.median_to_target?.value ?? 0));
  const rows: ChartRow[] = ok.map((r: OnboardingRole) => ({ id: r.role, label: shortName(r.name, 22), est: r.median_to_target ? { value: r.median_to_target.value, ci: r.median_to_target.ci } : null, tone: "neutral" as const }));
  const top = Math.max(0, ...rows.flatMap((r) => (r.est ? [r.est.value, ...(r.est.ci ?? [])] : [])));
  const { top: hi, ticks } = niceTop(top * 1.05, 2);
  return { rows, any: rows.length > 0, domain: [0, hi], ticks };
}

const sortHours = (rows: FirmRow[]): FirmRow[] => rows.filter((r) => fin(r.hours_per_week?.point) && r.hours_per_week.point > 0).sort((a, b) => b.hours_per_week.point - a.hours_per_week.point);
const hrs = (e: { point: number; lo: number; hi: number }): Est => ({ value: e.point, ci: fin(e.lo) && fin(e.hi) && e.lo <= e.hi ? [e.lo, e.hi] : null });
const f1 = (x: number): string => String(Math.round(x * 10) / 10);

/** Hours a week of the biggest repeated actions, with intervals, on one 0-based axis. */
export function hoursChart(rows: FirmRow[], n = 3): (ChartData & { any: boolean }) {
  const top = sortHours(rows).slice(0, n);
  const out: ChartRow[] = top.map((r) => ({ id: r.id, label: shortName(r.label, 24), est: hrs(r.hours_per_week), tone: "neutral" as const }));
  const hi = Math.max(0, ...out.flatMap((r) => (r.est ? [r.est.value, ...(r.est.ci ?? [])] : [])));
  const { top: axisTop, ticks } = niceTop(hi * 1.05, 2);
  return { rows: out, any: out.length > 0, domain: [0, axisTop], ticks };
}

/** The table behind the hours chart: the biggest actions with their interval, how many people do them, and how often. */
export function hitNumbers(rows: FirmRow[], limit = 30): { heads: string[]; rows: string[][] } {
  return {
    heads: ["Repeated action", "Hours a week (95% interval)", "People", "Times"],
    rows: sortHours(rows).slice(0, limit).map((r) => {
      const e = hrs(r.hours_per_week);
      return [shortName(r.label, 48), `${f1(e.value)} (${e.ci ? `${f1(e.ci[0])} to ${f1(e.ci[1])}` : "no interval yet"})`, fin(r.people) ? r.people.toLocaleString("en-GB") : "n/a", fin(r.count) ? r.count.toLocaleString("en-GB") : "n/a"];
    }),
  };
}

/** The table behind the onboarding chart: every role the engine followed, with the people count and how many reached the target. */
export function onboardingNumbers(data: WireOnboarding, min = MIN_N): { heads: string[]; rows: string[][] } {
  const unit = unitWord(data.x_unit);
  return {
    heads: ["Role", `Median ${unit === "steps" ? "step" : unit} to the target (95% interval)`, "People followed", "Reached it so far"],
    rows: data.roles.map((r) => {
      const m = r.median_to_target;
      const median = r.reason || r.n < min ? "not shown" : m ? `${r0(m.value)} (${m.ci ? `${r0(m.ci[0])} to ${r0(m.ci[1])}` : "no interval yet"})` : "fewer than half so far";
      return [shortName(r.name), median, fin(r.n) ? r.n.toLocaleString("en-GB") : "n/a", fmtShare(r.reached_share)];
    }),
  };
}
