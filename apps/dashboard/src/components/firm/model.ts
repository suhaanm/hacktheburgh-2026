// Pure logic for the Firm screens and the worker home: reading the insight routes tolerantly, formatting estimates with their
// intervals, grouping and sorting people (never ranking them), and the privacy threshold. No React and no network here, so all of
// it is tested without a browser.
import type {
  AdminInsight, CurvePoint, DrillColumn, DrillRow, Est, FirmAggregate, FirmRole, Interval, Origin, OnboardingRole, RoleCompare, RoleHabit,
  RoleMeasure, RoleSummary, TenureBand, Trend, UserRow, Verdict, WireDrill, WireFirm, WireOnboarding, WireOverview, WirePointer, WireRisk, WireRoles,
  WireSharing, WireWhy, WireWorker, PointerTarget,
} from "./wire";
import { TENURE_BANDS, TRENDS } from "./wire";

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => !!v && typeof v === "object" && !Array.isArray(v);
const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const str = (v: unknown): string | null => (typeof v === "string" && v.trim() ? v : null);
const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
const num = (v: unknown, d = 0): number => (isNum(v) ? v : d);

/* -- Reading ---------------------------------------------------------------------------------- */

/** An interval from `[lo, hi]`, `{lo, hi}` or `{low, high}`. Null when it is not a proper pair (lo above hi is swapped, not trusted blindly). */
export function interval(v: unknown): Interval | null {
  let lo: unknown, hi: unknown;
  if (Array.isArray(v) && v.length === 2) [lo, hi] = v;
  else if (isObj(v)) { lo = v.lo ?? v.low ?? v.lower; hi = v.hi ?? v.high ?? v.upper; }
  if (!isNum(lo) || !isNum(hi)) return null;
  return lo <= hi ? [lo, hi] : [hi, lo];
}

/** An estimate from a bare number, `{value, ci}`, `{point, lo, hi}`, `{mean, interval}` or `{share, wilson}`. */
export function est(v: unknown): Est | null {
  if (isNum(v)) return { value: v, ci: null };
  if (!isObj(v)) return null;
  const value = [v.value, v.point, v.mean, v.share, v.median, v.estimate].find(isNum);
  if (value === undefined) return null;
  const ci = interval(v.ci ?? v.interval ?? v.wilson ?? (isNum(v.lo) && isNum(v.hi) ? [v.lo, v.hi] : null));
  return { value: value as number, ci };
}

const origin = (v: unknown): Origin => (v === "real" || v === "mixed" ? v : "synthetic");
const verdict = (v: unknown): Verdict => (v === "gap" ? "gap" : "cannot_tell");
/** "steady" is the older spelling of "cannot_tell_yet". Anything unknown is "not enough data", never a guess. */
const trend = (v: unknown): Trend => (v === "steady" ? "cannot_tell_yet" : (TRENDS as unknown[]).includes(v) ? (v as Trend) : "not_enough_data");
const polarity = (v: unknown): "positive" | "attention" | "tradeoff" | "note" => (v === "positive" || v === "attention" || v === "tradeoff" ? v : "note");
const tenure = (v: unknown): TenureBand => ((TENURE_BANDS as unknown[]).includes(v) ? (v as TenureBand) : "lt_4w");

/** A body that came as `{meta, data}` or bare. */
export const dataOf = (body: unknown): unknown => (isObj(body) && "data" in body ? body.data : body);

export function pointer(v: unknown): WirePointer | null {
  if (!isObj(v)) return null;
  const id = str(v.id);
  const headline = str(v.headline);
  if (!id || !headline) return null;
  const a: Obj = isObj(v.action) ? v.action : {};
  const numbers: Record<string, number | string> = {};
  if (isObj(v.numbers)) for (const [k, x] of Object.entries(v.numbers)) if (isNum(x) || typeof x === "string") numbers[k] = x;
  return {
    id, kind: str(v.kind) ?? "habit", headline, detail: str(v.detail), numbers, origin: origin(v.origin), n: isNum(v.n) ? v.n : null, n_unit: str(v.n_unit),
    polarity: polarity(v.polarity), polarity_label: str(v.polarity_label), glyph: str(v.glyph), a11y_label: str(v.a11y_label), badge: str(v.badge),
    details_available: v.details_available !== false,
    action: str(a.to) ? { label: str(a.label) ?? "Open", to: str(a.to) as PointerTarget, query: str(a.query) } : null,
  };
}

export function normaliseWorker(body: unknown): WireWorker {
  const d = dataOf(body);
  const o = isObj(d) ? d : {};
  const pointers = arr(o.pointers).map(pointer).filter((p): p is WirePointer => !!p).slice(0, 3); // never more than three
  const t = isObj(o.try) && str(o.try.label) && isNum(o.try.value) ? { label: str(o.try.label) as string, value: o.try.value as number, unit: str(o.try.unit) ?? "" } : null;
  const w = isObj(o.week) ? o.week : null;
  return {
    person: str(o.person), role: str(o.role), week: w && str(w.from) && str(w.to) ? { from: str(w.from) as string, to: str(w.to) as string } : null,
    nothing_stands_out: o.nothing_stands_out === true || pointers.length === 0, stand_in: o.stand_in === true, pointers, try: t, monday_note: str(o.monday_note),
    status: str(o.status) ?? (pointers.length === 0 ? "nothing_stands_out" : "ok"), message: str(o.message),
  };
}

export function normaliseWhy(body: unknown): WireWhy {
  const o = (isObj(dataOf(body)) ? dataOf(body) : {}) as Obj;
  return {
    id: str(o.id) ?? "", headline: str(o.headline) ?? "",
    because: arr(o.because).filter((x): x is string => typeof x === "string"),
    sources: arr(o.sources).filter(isObj).map((s) => ({ label: str(s.label) ?? "", n: isNum(s.n) ? s.n : null, n_unit: str(s.n_unit), origin: origin(s.origin) })),
    limits: arr(o.limits).filter((x): x is string => typeof x === "string"),
    state: str(o.state), reason_text: str(o.reason_text),
  };
}

export function normaliseSharing(body: unknown): WireSharing {
  const o = (isObj(dataOf(body)) ? dataOf(body) : {}) as Obj;
  const kinds = ["number", "enum", "count"];
  return {
    items: arr(o.items).filter(isObj).filter((i) => str(i.label)).map((i, k) => ({ id: str(i.id) ?? `item-${k}`, label: str(i.label) as string, kind: (kinds.includes(i.kind as string) ? i.kind : "number") as "number" | "enum" | "count", note: str(i.note) })),
    never: arr(o.never).filter((x): x is string => typeof x === "string"),
    notice: str(o.notice), preview: isObj(o.preview) ? o.preview : null, visible_since: str(o.visible_since), visible_to: str(o.visible_to), legal_note: str(o.legal_note),
  };
}

export function insight(v: unknown): AdminInsight | null {
  if (!isObj(v)) return null;
  const id = str(v.id), headline = str(v.headline);
  if (!id || !headline) return null;
  const e = isObj(v.effect) && isNum(v.effect.value) ? { label: str(v.effect.label) ?? "", unit: str(v.effect.unit) ?? "", value: v.effect.value, ci: interval(v.effect.ci ?? v.effect.interval) } : null;
  return {
    id, headline, role: str(v.role) ?? "all", effect: e, n: num(v.n), n_unit: str(v.n_unit) ?? "people", origin: origin(v.origin), drill: str(v.drill) ?? id,
    kind: str(v.kind), polarity: polarity(v.polarity), polarity_label: str(v.polarity_label), glyph: str(v.glyph), a11y_label: str(v.a11y_label),
    position: isNum(v.position) ? v.position : null, text: str(v.text), badge: str(v.badge), split: str(v.split), statement: str(v.statement),
    action: isObj(v.action) && str(v.action.to) ? { id: str(v.action.id) ?? "open", label: str(v.action.label) ?? "Open", to: str(v.action.to) as string, query: str(v.action.query) } : null,
  };
}

export function normaliseRisk(v: unknown): WireRisk | null {
  if (!isObj(v)) return null;
  const a = isObj(v.approval_backlog_age_h) && isNum(v.approval_backlog_age_h.median) ? { median: v.approval_backlog_age_h.median, max: num(v.approval_backlog_age_h.max, v.approval_backlog_age_h.median) } : null;
  return { approval_backlog_age_h: a, injection_pauses_30d: num(v.injection_pauses_30d), kill_events_30d: num(v.kill_events_30d), open_approvals: num(v.open_approvals) };
}

function roleSummary(v: unknown): RoleSummary | null {
  if (!isObj(v) || !str(v.role)) return null;
  const t = isObj(v.trend) ? v.trend : null;
  return {
    role: str(v.role) as string, name: str(v.name) ?? (str(v.role) as string), people: num(v.people), enough: v.enough !== false, n_expert: num(v.n_expert), n_junior: num(v.n_junior),
    reason: str(v.reason), gap: est(v.gap), trend: t ? { cls: trend(t.class), label: str(t.label) } : null,
  };
}

export function normaliseOverview(body: unknown): WireOverview {
  const o = (isObj(dataOf(body)) ? dataOf(body) : {}) as Obj;
  const f = isObj(o.firm) ? o.firm : {};
  const c = isObj(o.coverage) ? o.coverage : {};
  const sup = isObj(o.suppressed) ? o.suppressed : null;
  const counts = (v: unknown): Record<string, number> => { const out: Record<string, number> = {}; if (isObj(v)) for (const [k, x] of Object.entries(v)) if (isNum(x)) out[k] = x; return out; };
  return {
    firm: { users: num(f.users), roles: num(f.roles), label: str(f.label) ?? "synthetic firm" },
    top: arr(o.top).map(insight).filter((i): i is AdminInsight => !!i).slice(0, 7),
    coverage: {
      users: num(c.users), enough_data: num(c.enough_data), min_occurrences: num(c.min_occurrences, 20), by_status: counts(c.by_status),
      roles: arr(c.roles).filter(isObj).filter((r) => str(r.role)).map((r) => ({ role: str(r.role) as string, name: str(r.name) ?? (str(r.role) as string), users: num(r.users), enough_data: num(r.enough_data) })),
    },
    risk: normaliseRisk(o.risk),
    role_comparison: arr(o.role_comparison).map(roleSummary).filter((r): r is RoleSummary => !!r),
    suppressed: sup ? { count: num(sup.count), by_reason: counts(sup.by_reason) } : null,
    statement: str(o.statement),
  };
}

function drillColumns(v: unknown): DrillColumn[] {
  return arr(v).filter(isObj).filter((c) => str(c.key)).map((c) => ({ key: str(c.key) as string, label: str(c.label) ?? (str(c.key) as string), unit: str(c.unit) }));
}
function drillRows(v: unknown): DrillRow[] {
  return arr(v).filter(isObj).filter((r) => str(r.label)).map((r) => {
    const values: DrillRow["values"] = {};
    if (isObj(r.values)) {
      for (const [k, x] of Object.entries(r.values)) {
        if (isNum(x) || typeof x === "string" || x === null) values[k] = x as number | string | null;
        else { const iv = interval(x); if (iv) values[k] = iv; }
      }
    }
    return { label: str(r.label) as string, name: str(r.name), group: str(r.group), values, n: isNum(r.n) ? r.n : null };
  });
}

export function normaliseDrill(body: unknown): WireDrill {
  const o = (isObj(dataOf(body)) ? dataOf(body) : {}) as Obj;
  const columns = drillColumns(o.columns);
  const rows = drillRows(o.rows);
  const tables = arr(o.tables).filter(isObj).map((t, i) => ({ id: str(t.id) ?? `t${i}`, title: str(t.title) ?? "", columns: drillColumns(t.columns), rows: drillRows(t.rows) })).filter((t) => t.columns.length && t.rows.length);
  const series = arr(o.series).filter(isObj).map((s) => ({
    label: str(s.label) ?? "",
    points: arr(s.points).filter(isObj).filter((p) => isNum(p.x) && isNum(p.y)).map((p) => ({ x: p.x as number, y: p.y as number, lo: isNum(p.lo) ? p.lo : null, hi: isNum(p.hi) ? p.hi : null })),
  }));
  return { id: str(o.id) ?? "", headline: str(o.headline) ?? "", columns, rows, series, notes: arr(o.notes).filter((x): x is string => typeof x === "string"), tables, method: str(o.method) };
}

function measure(v: unknown): RoleMeasure | null {
  if (!isObj(v) || !str(v.key)) return null;
  return { key: str(v.key) as string, label: str(v.label) ?? (str(v.key) as string), unit: str(v.unit) ?? "share", expert: est(v.expert), junior: est(v.junior), gap: est(v.gap), verdict: verdict(v.verdict) };
}
function habit(v: unknown): RoleHabit | null {
  if (!isObj(v) || !str(v.label)) return null;
  return { id: str(v.id) ?? (str(v.label) as string), label: str(v.label) as string, explains_s: est(v.explains_s), expert_rate: est(v.expert_rate), junior_rate: est(v.junior_rate), n: num(v.n), verdict: verdict(v.verdict) };
}

export function normaliseRoles(body: unknown): WireRoles {
  const o = (isObj(dataOf(body)) ? dataOf(body) : {}) as Obj;
  const roles: RoleCompare[] = arr(o.roles).filter(isObj).filter((r) => str(r.role)).map((r) => ({
    role: str(r.role) as string, name: str(r.name) ?? (str(r.role) as string), n_expert: num(r.n_expert), n_junior: num(r.n_junior),
    enough: r.enough !== false, reason: str(r.reason), standard: str(r.standard), measures: arr(r.measures).map(measure).filter((m): m is RoleMeasure => !!m), habits: arr(r.habits).map(habit).filter((h): h is RoleHabit => !!h),
  }));
  const s = isObj(o.same_scale) ? o.same_scale : {};
  return { roles, same_scale: { min: num(s.min, 0), max: num(s.max, 1) } };
}

export function userRow(v: unknown): UserRow | null {
  if (!isObj(v) || !str(v.id)) return null;
  const t = isObj(v.time_to_independence) ? v.time_to_independence : {};
  const skills = arr(v.skills).filter(isObj).filter((k) => str(k.skill) || str(k.label)).map((k) => ({
    skill: str(k.skill) ?? (str(k.label) as string), label: str(k.label) ?? (str(k.skill) as string), n: num(k.n), independence_share: isNum(k.independence_share) ? k.independence_share : null, lost_s: est(k.lost_s),
  }));
  return {
    id: str(v.id) as string, label: str(v.label) ?? (str(v.id) as string), name: str(v.name), role: str(v.role), level: v.level === "expert" || v.level === "junior" ? v.level : null, status: str(v.status),
    last_seen_days: isNum(v.last_seen_days) ? v.last_seen_days : null, skills, tenure_band: tenure(v.tenure_band), tenure_weeks: isNum(v.tenure_weeks) ? v.tenure_weeks : null,
    trend: trend(v.trend), independence: est(v.independence), assisted_share: est(v.assisted_share),
    time_to_independence: { reached: t.reached === true, value: isNum(t.value) ? t.value : null, unit: str(t.unit) ?? "occurrences" },
    automations_running: num(v.automations_running), n: num(v.n), n_recent: isNum(v.n_recent) ? v.n_recent : null,
    automation: isObj(v.automation) ? { minutes: num(v.automation.minutes), routines_approved: num(v.automation.routines_approved), runs_done: num(v.automation.runs_done) } : null,
  };
}
function aggregate(v: unknown, users: number): FirmAggregate {
  const o = isObj(v) ? v : {};
  const t = isObj(o.time_to_independence) ? o.time_to_independence : {};
  return {
    n_users: num(o.n_users, users), independence: est(o.independence), assisted_share: est(o.assisted_share),
    time_to_independence: { median: isNum(t.median) ? t.median : null, ci: interval(t.ci), unit: str(t.unit) ?? "occurrences", reached_share: est(t.reached_share) },
  };
}

export function normaliseFirm(body: unknown): WireFirm {
  const o = (isObj(dataOf(body)) ? dataOf(body) : {}) as Obj;
  const roles: FirmRole[] = arr(o.roles).filter(isObj).filter((r) => str(r.role)).map((r) => {
    const users = arr(r.users).map(userRow).filter((u): u is UserRow => !!u);
    const t = isObj(r.trend) ? r.trend : null;
    return {
      role: str(r.role) as string, name: str(r.name) ?? (str(r.role) as string), merged: r.merged === true, users, aggregate: aggregate(r.aggregate, users.length),
      trend: t ? { cls: trend(t.class), label: str(t.label), n_people: isNum(t.n_people) ? t.n_people : null, slope_per_4w: est(t.slope_per_4w) } : null,
    };
  });
  const p = isObj(o.privacy) ? o.privacy : {};
  const t = isObj(o.totals) ? o.totals : {};
  const all = roles.reduce((a, r) => a + r.users.length, 0);
  return {
    roles, privacy: { min_group: num(p.min_group, 5), merged_roles: arr(p.merged_roles).filter((x): x is string => typeof x === "string"), note: str(p.note) },
    totals: { users: num(t.users, all), enough_data: num(t.enough_data, roles.reduce((a, r) => a + r.users.filter((u) => u.trend !== "not_enough_data").length, 0)) },
  };
}

export function normaliseOnboarding(body: unknown): WireOnboarding {
  const o = (isObj(dataOf(body)) ? dataOf(body) : {}) as Obj;
  const t = isObj(o.target) ? o.target : {};
  const points = (v: unknown): CurvePoint[] => arr(v).filter(isObj).filter((p) => isNum(p.x) && isNum(p.y)).map((p): CurvePoint => ({ x: p.x as number, y: p.y as number, lo: num(p.lo, p.y as number), hi: num(p.hi, p.y as number), n: isNum(p.n) ? p.n : isNum(p.n_at_risk) ? p.n_at_risk : null }));
  const roles: OnboardingRole[] = arr(o.roles).filter(isObj).filter((r) => str(r.role)).map((r) => ({
    role: str(r.role) as string, name: str(r.name) ?? (str(r.role) as string), n: num(r.n),
    curve: points(r.curve), km: points(r.km), censored: isNum(r.censored) ? r.censored : null, reason: str(r.reason), at_risk_at_target: isNum(r.at_risk_at_target) ? r.at_risk_at_target : null,
    median_to_target: est(r.median_to_target), reached_share: est(r.reached_share),
  }));
  return {
    target: { value: num(t.value, 0.8), label: str(t.label) ?? "design target", rule: str(t.rule), note: str(t.note), occurrences: isNum(t.occurrences) ? t.occurrences : null },
    method: str(o.method), x_unit: str(o.x_unit) ?? "occurrences", roles,
  };
}

/* -- Formatting -------------------------------------------------------------------------------- */

/** The wire says "occurrences"; the Firm screens say "steps", as everywhere else people read them. */
export const unitWord = (u: string): string => (u === "occurrences" ? "steps" : u);

/** 0.624 -> "62%". */
export const pct = (x: number): string => `${Math.round(x * 100)}%`;
const trim = (x: number): string => (Math.abs(x) >= 100 ? String(Math.round(x)) : String(Math.round(x * 10) / 10));

/** "62% (54% to 70%)" or "62% (no interval yet)". Words, not a dash, so a screen reader reads a range. */
export function fmtShare(e: Est | null): string {
  if (!e) return "not enough data";
  return e.ci ? `${pct(e.value)} (${pct(e.ci[0])} to ${pct(e.ci[1])})` : `${pct(e.value)} (no interval yet)`;
}
export function fmtNum(e: Est | null, unit = ""): string {
  if (!e) return "not enough data";
  const u = unit ? ` ${unit}` : "";
  return e.ci ? `${trim(e.value)}${u} (${trim(e.ci[0])} to ${trim(e.ci[1])})` : `${trim(e.value)}${u} (no interval yet)`;
}
/** A signed number for a gap: "+0.21" or "-12". */
export const signed = (x: number, digits = 2): string => `${x > 0 ? "+" : x < 0 ? "-" : ""}${Math.abs(x).toFixed(digits)}`;

/** Does this interval include zero? Then the sign of the estimate cannot be read. */
export const spansZero = (ci: Interval | null): boolean => !!ci && ci[0] <= 0 && ci[1] >= 0;

export const TREND_LABEL: Record<Trend, string> = {
  improving: "Improving", cannot_tell_yet: "Cannot tell yet", needs_attention: "Needs attention", not_enough_data: "Not enough data",
};
/** A word and a glyph for each class, so the class is never carried by colour alone. */
export const TREND_GLYPH: Record<Trend, string> = { improving: "↗", cannot_tell_yet: "→", needs_attention: "!", not_enough_data: "·" };
export const TREND_HINT: Record<Trend, string> = {
  improving: "The help this person needs has been falling, and the interval says so.",
  cannot_tell_yet: "No change we can tell yet. The interval on the trend includes zero, so this is not the same as no change.",
  needs_attention: "The help this person needs has not fallen as it usually does by this point. Worth a conversation, not a verdict.",
  not_enough_data: "Fewer occurrences than the minimum, so no trend is shown.",
};

export const TENURE_LABEL: Record<TenureBand, string> = { lt_4w: "under 4 weeks", "1_3m": "1 to 3 months", "3_6m": "3 to 6 months", "6_12m": "6 to 12 months", "12m_plus": "over a year" };
const TENURE_ORDER: Record<TenureBand, number> = { lt_4w: 0, "1_3m": 1, "3_6m": 2, "6_12m": 3, "12m_plus": 4 };

export const ROLE_SHORT: Record<string, string> = { "benefits-processor": "Benefits", "data-analyst": "Data", programmer: "Programming" };

/* -- People: grouped, sorted by name or tenure, never ranked ---------------------------------- */

/** The only two sort keys. There is deliberately no "best", "score" or "rank": the page is for coaching and onboarding, not for evaluating individuals. */
export type SortKey = "name" | "tenure";
export const SORT_KEYS: SortKey[] = ["name", "tenure"];
export const DEFAULT_SORT: SortKey = "name";

/** What to show for a person: their made-up name when the row has one, else the stable label. The label stays the key and the aria id. */
export const personName = (p: { name?: string | null; label?: string | null } | null | undefined): string => p?.name?.trim() || p?.label || "";

/** A natural compare on what is shown, so "BP-07" comes before "BP-10" and names run A to Z. */
const byLabel = (a: UserRow, b: UserRow): number => personName(a).localeCompare(personName(b), "en", { numeric: true, sensitivity: "base" }) || a.label.localeCompare(b.label, "en", { numeric: true });

/** A new array. By name, A to Z; or by tenure, longest first, ties by name. */
export function sortUsers(users: UserRow[], by: SortKey = DEFAULT_SORT): UserRow[] {
  const copy = [...users];
  if (by === "tenure") {
    copy.sort((a, b) => (b.tenure_weeks ?? TENURE_ORDER[b.tenure_band] * 13) - (a.tenure_weeks ?? TENURE_ORDER[a.tenure_band] * 13) || byLabel(a, b));
  } else copy.sort(byLabel);
  return copy;
}

/** A class filter (not a ranking): show only one trend class, or all of them. */
export const filterUsers = (users: UserRow[], t: Trend | null): UserRow[] => (t ? users.filter((u) => u.trend === t) : users);

export function trendCounts(users: UserRow[]): Record<Trend, number> {
  const c: Record<Trend, number> = { improving: 0, cannot_tell_yet: 0, needs_attention: 0, not_enough_data: 0 };
  for (const u of users) c[u.trend] += 1;
  return c;
}

/**
 * The privacy threshold for comparison tables: a role aggregate is shown only when the group has at least `min` people (default 5).
 * The engine merges small groups itself; this is the second check on the page, so a small group's figure is never drawn.
 */
export const groupShown = (r: Pick<FirmRole, "aggregate" | "users" | "merged">, min: number): boolean => !r.merged && Math.max(r.aggregate.n_users, r.users.length) >= min;

/** For a role comparison: both groups need at least `min` people. */
export const compareShown = (r: Pick<RoleCompare, "n_expert" | "n_junior" | "enough">, min: number): boolean => r.enough && r.n_expert >= min && r.n_junior >= min;

/** Roles under the threshold, merged into one name for the note. */
export const smallRoles = (roles: Pick<FirmRole, "role" | "name" | "aggregate" | "users" | "merged">[], min: number): string[] => roles.filter((r) => !groupShown(r, min)).map((r) => r.name);

/* -- Onboarding curves ------------------------------------------------------------------------- */

/** Points with fewer than `min` people still in view are cut: past that the curve describes two or three people. */
export const trimCurve = (points: CurvePoint[], min = 5): CurvePoint[] => points.filter((p) => p.n === null || p.n >= min).sort((a, b) => a.x - b.x);

/** First x where the curve's lower bound reaches the target and stays there. Null when it never does. Read from the curve, so it can be checked. */
export function crossing(points: CurvePoint[], target: number): number | null {
  const ps = [...points].sort((a, b) => a.x - b.x);
  for (let i = 0; i < ps.length; i++) if (ps.slice(i).every((p) => p.lo >= target)) return ps[i].x;
  return null;
}

/* -- Overview ---------------------------------------------------------------------------------- */

export function effectText(e: AdminInsight["effect"]): string | null {
  if (!e) return null;
  // An exact count has no interval to give, and its headline already says it: show nothing rather than "(no interval yet)".
  if (!e.ci && e.unit === "count") return null;
  const u = e.unit === "share" ? "" : e.unit === "points" ? " points" : e.unit ? ` ${e.unit}` : "";
  const f = (x: number) => (e.unit === "share" ? pct(x) : trim(x));
  if (!e.ci) return e.unit === "hours" || e.unit === "minutes" ? `${f(e.value)}${u}` : `${f(e.value)}${u} (no interval yet)`;
  return `${f(e.value)}${u} (${f(e.ci[0])} to ${f(e.ci[1])})`;
}

export const coverageShare = (c: WireOverview["coverage"]): number => (c.users > 0 ? c.enough_data / c.users : 0);

/** One word for how far the interval supports a claim: "gap" or "cannot tell yet". */
export const verdictText = (v: Verdict): string => (v === "gap" ? "A gap we can see" : "Cannot tell yet");

/** Origin badge words. */
export const originWord = (o: Origin): string => (o === "real" ? "real" : o);

/* -- The worker's own transparency view ---------------------------------------------------------------------------------------- */

const LEVEL_WORD: Record<string, string> = { expert: "expert", junior: "junior" };
const ROLE_WORD: Record<string, string> = { "benefits-processor": "Benefits processor", "data-analyst": "Data analyst", programmer: "Programmer" };
export const roleWord = (role: string | null | undefined): string => (role ? ROLE_WORD[role] ?? role : "");

/**
 * The exact summary an admin sees about a worker, as label and value lines. Numbers carry their intervals (the admin's view prints them) and
 * nothing here is a score or a rank. Returns [] for a preview the page cannot read.
 */
export function previewLines(preview: Record<string, unknown> | null): [string, string][] {
  const u = preview ? userRow(preview) : null;
  if (!u) return [];
  const lines: [string, string][] = [];
  lines.push(["Shown as", personName(u)]);
  if (u.role) lines.push(["Role", `${roleWord(u.role)}${u.level ? `, ${LEVEL_WORD[u.level]}` : ""}`]);
  lines.push(["Time in role", TENURE_LABEL[u.tenure_band]]);
  lines.push(["Help needed over time", TREND_LABEL[u.trend]]);
  lines.push(["Finished without help, recent steps", fmtShare(u.independence)]);
  lines.push(["Needed help, all steps", fmtShare(u.assisted_share)]);
  const t = u.time_to_independence;
  lines.push(["Steps until you stopped needing help", t.reached && t.value !== null ? `${trim(t.value)} ${t.unit}` : "not reached yet"]);
  lines.push(["Routines running", String(u.automations_running)]);
  lines.push(["Steps counted", String(u.n)]);
  if (u.last_seen_days !== null) lines.push(["Last seen", u.last_seen_days === 0 ? "today" : `${u.last_seen_days} ${u.last_seen_days === 1 ? "day" : "days"} ago`]);
  return lines;
}

/* -- Drill-down tables ------------------------------------------------------------------------------------------------------- */

const isCiKey = (k: string): boolean => /(^|_)ci$/.test(k);

/** One cell: the number in its unit, with the interval beside it when there is one. A share is shown as a percentage. */
export function fmtCell(value: unknown, unit: string | null, ci: Interval | null = null): string {
  const one = (x: number): string => (unit === "share" ? pct(x) : unit === "seconds" ? `${trim(x)} s` : unit === "hours" ? `${trim(x)} h` : trim(x));
  if (value === null || value === undefined) return "not enough data";
  if (typeof value === "string") return value;
  if (Array.isArray(value) && value.length === 2 && isNum(value[0]) && isNum(value[1])) return `${one(value[0])} to ${one(value[1])}`;
  if (!isNum(value)) return "not enough data";
  return ci ? `${one(value)} (${one(ci[0])} to ${one(ci[1])})` : one(value);
}

export interface DrillView { heads: { key: string; label: string }[]; rows: { label: string; n: number | null; group: string | null; cells: string[] }[] }

/**
 * A drill-down table ready to print. An interval column ("gap_ci", or plain "ci" for the first value column) is folded into the figure it belongs to,
 * so the reader sees "38.3 s (35.5 to 41.1)" in one cell instead of a separate column of pairs.
 */
export function drillTable(columns: DrillColumn[], rows: DrillRow[]): DrillView {
  const values = columns.filter((c) => !isCiKey(c.key));
  const owner = (ci: DrillColumn): string | null => (ci.key === "ci" ? values[0]?.key ?? null : ci.key.replace(/_ci$/, ""));
  const ciFor = new Map<string, DrillColumn>();
  for (const c of columns) if (isCiKey(c.key)) { const o = owner(c); if (o && values.some((v) => v.key === o)) ciFor.set(o, c); }
  const shown = columns.filter((c) => !isCiKey(c.key) || ![...ciFor.values()].includes(c));
  return {
    heads: shown.map((c) => ({ key: c.key, label: c.label })),
    rows: rows.map((r) => ({
      label: personName(r), n: r.n, group: r.group,
      cells: shown.map((c) => {
        const iv = ciFor.get(c.key);
        const ci = iv ? interval(r.values[iv.key]) : null;
        return fmtCell(r.values[c.key], c.unit, ci);
      }),
    })),
  };
}

/* -- Role comparison words --------------------------------------------------------------------------------------------------- */

const points = (v: number): string => `${v > 0 ? "+" : v < 0 ? "-" : ""}${Math.abs(Math.round(v * 100))}`;

/**
 * The gap between juniors and experts in one or two plain sentences. A gap whose interval spans zero is said to be unreadable, not small.
 * `independence` is a share (the gap is in share units); `time` is seconds per case beyond the experts.
 */
export function roleGapLine(independence: RoleMeasure | undefined, time: RoleMeasure | undefined): string {
  const parts: string[] = [];
  const g = independence?.gap;
  if (g) {
    const dir = g.value < 0 ? "fewer" : "more";
    const iv = g.ci ? ` (${points(g.ci[0])} to ${points(g.ci[1])} points)` : " (no interval yet)";
    parts.push(`Juniors finish ${Math.abs(Math.round(g.value * 100))} points ${dir} of their steps without help${iv}.`);
  }
  const t = time?.gap;
  if (t) parts.push(`They take ${fmtNum(t, "s")} ${t.value >= 0 ? "more" : "less"} per case.`);
  if (parts.length === 0) return "";
  if (independence && independence.verdict !== "gap") parts.push("We cannot tell yet whether this is a real gap.");
  return parts.join(" ");
}
