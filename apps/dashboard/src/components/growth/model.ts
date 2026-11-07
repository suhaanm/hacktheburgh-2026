// Pure adapters and copy for the Growth screen ("Curtain"). No React, no fetch: everything the page says
// is built here from the wire data, so the numbers in the sentences are always the data's numbers.
import type { Direction, Interval, LedgerRow, OriginDetail, WireCurvePoint, WireGrowth, WireMedian, WireRecent, WireRetention, WireSkill } from "./wire";

/** Spec constants the screen quotes. The engine decides the real thresholds; these only word the empty state. */
export const BASELINE_N = 5;
export const RETENTION_DAYS = 3;
export const DEFAULT_NEEDED = 10;
export const DEFAULT_WINDOW = 20;
export const RECENT_N = 10;

const MINUS = "−";

export const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;
export const timesWord = (n: number) => (n === 1 ? "1 time" : `${n} times`);

export function signed(n: number, digits = 0): string {
  const v = Math.abs(n).toFixed(digits);
  return n < 0 && Number(v) !== 0 ? `${MINUS}${v}` : v;
}
/** +6.2, 0, −3.1 (a plus sign makes a change read as a change). */
export function change(n: number, digits = 0): string {
  const s = signed(n, digits);
  return n > 0 && Number(s) !== 0 ? `+${s}` : s;
}
export const pct = (p: number, digits = 0): string => `${signed(p * 100, digits)}%`;
/** "48 to 86%" for running text. */
export const pctRange = (iv: Interval, digits = 0): string => `${signed(iv[0] * 100, digits)} to ${signed(iv[1] * 100, digits)}%`;
/** "[48, 86]%" for data lines. */
export const pctBracket = (iv: Interval, digits = 0): string => `[${signed(iv[0] * 100, digits)}, ${signed(iv[1] * 100, digits)}]%`;

/** "2026-11-07T17" (hour bucket) or a full ISO string, read as UTC. */
export function parseHour(t: string): Date {
  const d = new Date(/T\d\d$/.test(t) ? `${t}:00:00Z` : t);
  return d;
}
export function fmtDay(t: string): string {
  const d = parseHour(t);
  if (Number.isNaN(d.getTime())) return t;
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
}
export function fmtDayHour(t: string): string {
  const d = parseHour(t);
  if (Number.isNaN(d.getTime())) return t;
  const day = d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });
  const hh = d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "UTC" });
  return `${day}, ${hh}`;
}

/* -- Normalise: tolerate a slightly different or partial answer ------------------------------------ */
/** The engine's first draft said "flat" and "unclear"; the agreed words are "steady" and "too_early". Anything else is "too_early". */
export function directionOf(d: unknown): Direction {
  if (d === "less_help" || d === "more_help" || d === "steady" || d === "too_early") return d;
  if (d === "flat") return "steady";
  return "too_early";
}

/** Fill what is missing so the screen never has to guess; absent numbers stay null, never 0. */
export function normalizeGrowth(raw: Partial<WireGrowth>): WireGrowth {
  const occ = raw.occurrences ?? { total: raw.readiness?.occurrences ?? 0, unaided: 0, assisted: 0, errors: 0, abandoned: 0 };
  const total = raw.readiness?.occurrences ?? occ.total ?? 0;
  const ready = raw.readiness?.ready ?? total >= DEFAULT_NEEDED;
  const sc = raw.score;
  return {
    person: raw.person ?? "",
    skill: raw.skill ?? null,
    window: raw.window ?? DEFAULT_WINDOW,
    origin_detail: raw.origin_detail,
    readiness: { occurrences: total, needed: raw.readiness?.needed ?? DEFAULT_NEEDED, ready, trend_needed: raw.readiness?.trend_needed },
    baseline: raw.baseline && raw.baseline.share != null && raw.baseline.wilson ? raw.baseline : null,
    score: {
      composite: sc?.composite_experimental ?? sc?.composite ?? null,
      composite_ci: sc?.composite_experimental_ci ?? sc?.composite_ci ?? null,
      composite_partial: sc?.composite_partial ?? false,
      available_weight: sc?.available_weight ?? 1,
      weights: sc?.weights ?? { independence_lb: 0.4, mastery: 0.3, gap_closure: 0.2, retention: 0.1 },
      used_weights: sc?.used_weights && Object.keys(sc.used_weights).length ? sc.used_weights : null,
      weights_note: sc?.weights_note ?? "Stated assumptions, not fitted.",
      composite_caveat: sc?.composite_caveat ?? null,
      composite_caveat_figures: sc?.composite_caveat_figures ?? null,
    },
    components: {
      independence: raw.components?.independence && raw.components.independence.share != null && raw.components.independence.wilson ? raw.components.independence : null,
      mastery: raw.components?.mastery ?? null,
      gap_closure: raw.components?.gap_closure ?? null,
      retention: raw.components?.retention ?? null,
    },
    trend: {
      slope_per_10: raw.trend?.slope_per_10 ?? null, ci: raw.trend?.ci ?? null, direction: directionOf(raw.trend?.direction), blocks: raw.trend?.blocks ?? [],
      needed_more: raw.trend?.needed_more ?? null, power_note: raw.trend?.power_note ?? null,
    },
    curve: raw.curve ?? [],
    occurrences: occ,
    time_to_progress: raw.time_to_progress ?? null,
    by_skill: (raw.by_skill ?? []).map((s) => ({
      ...s,
      label: s.label || humanise(s.skill),
      name: s.name || s.label || humanise(s.skill),
      independent: s.independent ?? 0,
      assisted: s.assisted ?? 0,
      direction: directionOf(s.direction),
      retrieval_due: !!s.retrieval_due,
      first10: s.first10 ?? null,
      last10: s.last10 ?? null,
      time_to_progress: s.time_to_progress ?? null,
      retention: s.retention ?? null,
      independence_lower: s.independence_lower ?? null,
      mastery: s.mastery ?? null,
      level: s.level ?? null,
    })),
    offloaded: { delegated: raw.offloaded?.delegated ?? 0, automation: raw.offloaded?.automation ?? 0, minutes: raw.offloaded?.minutes, by_skill: raw.offloaded?.by_skill, note: raw.offloaded?.note },
    counts: raw.counts,
    claim: raw.claim,
  };
}

/* -- Status ------------------------------------------------------------------------------------ */
export type Status = "empty" | "early" | "ready";

export function statusOf(w: WireGrowth): Status {
  const total = w.readiness?.occurrences ?? w.occurrences?.total ?? 0;
  if (total <= 0) return "empty";
  const ready = w.readiness ? w.readiness.ready : total >= DEFAULT_NEEDED;
  return ready && w.curve.length > 0 ? "ready" : "early";
}

/* -- Direction and trend ----------------------------------------------------------------------- */
/** The engine reports the change in the ASSISTED share (negative = needs less help). The page speaks of independence (positive = better). */
export function improvement(trend: WireGrowth["trend"]): { per10: number | null; ci: Interval | null } {
  const per10 = trend.slope_per_10 == null ? null : -trend.slope_per_10 * 100;
  const ci: Interval | null = trend.ci ? [-trend.ci[1] * 100, -trend.ci[0] * 100] : null;
  return { per10: per10 === 0 ? 0 : per10, ci };
}

const pts = (n: number) => change(n, Math.abs(n) < 10 ? 1 : 0);

/**
 * How many more occurrences before a real change would usually be seen. The engine's own figure when it sends one; while the trend
 * cannot be computed at all, what is left of `readiness.trend_needed`; otherwise 0 (nothing is known to be missing).
 */
export function stillNeeded(w: Pick<WireGrowth, "readiness" | "trend">): number {
  const own = w.trend?.needed_more;
  if (own != null && own > 0) return Math.round(own);
  if (w.trend?.direction === "too_early" && w.readiness?.trend_needed != null) return Math.max(0, w.readiness.trend_needed - (w.readiness.occurrences ?? 0));
  return 0;
}

/**
 * The trend in words. A trend whose interval includes zero is never "no change": at these sample sizes a real improvement is often
 * missed, so the page says it cannot tell yet. The engine's own sentence about power is printed verbatim when it sends one.
 */
export function trendSentence(trend: WireGrowth["trend"], levelPct = 95, more = 0, trendNeeded: number | null = null, have = 0): string {
  const { per10, ci } = improvement(trend);
  if (trend.direction === "too_early" || per10 == null || !ci) {
    const need = trend.power_note ? ` ${trend.power_note}` : trendNeeded != null && trendNeeded > have ? ` A trend needs ${trendNeeded} occurrences and you have ${have}.` : "";
    return `Too early for a trend.${need}`;
  }
  const a = Math.abs(per10).toFixed(Math.abs(per10) < 10 ? 1 : 0);
  const range = `${levelPct}% interval ${pts(ci[0])} to ${pts(ci[1])} points`;
  if (trend.direction === "less_help") return `About ${a} points more of your occurrences finish with no cue for every 10 more (${range}).`;
  if (trend.direction === "more_help") return `About ${a} points fewer of your occurrences finish with no cue for every 10 more (${range}).`;
  const note = trend.power_note ?? "";
  const lead = /cannot tell/i.test(note) ? "" : "Cannot tell yet. ";
  const fact = `The ${levelPct}% interval runs from ${pts(ci[0])} to ${pts(ci[1])} points per 10 occurrences and includes zero.`;
  const middle = note ? ` ${note}` : " With this few occurrences a real change is often missed, so this is not a finding that nothing is changing.";
  const tail = more > 0 && !note.includes(String(more)) ? ` About ${plural(more, "more occurrence")} would help.` : "";
  return `${lead}${fact}${middle}${tail}`;
}

export const DIRECTION_WORD: Record<Direction, string> = {
  less_help: "needs less help",
  steady: "cannot tell yet",
  more_help: "needs more help",
  too_early: "too early to say",
};

export function heroTitle(status: Status, direction: Direction, name: string | null): string {
  if (status === "empty") return "Nothing to show yet";
  if (status === "early" || direction === "too_early") return name ? `Too early to say how much help you need with ${name}` : "Too early to say how much help you need";
  if (direction === "less_help") return name ? `You need less help with ${name}` : "You need help less often than you did";
  if (direction === "more_help") return name ? `You have needed more help with ${name} lately` : "You have needed more help lately";
  return name ? `Cannot tell yet whether you need less help with ${name}` : "Cannot tell yet whether you need less help";
}

/* -- Sentences from counts --------------------------------------------------------------------- */
/** "You needed help with the cliff check 7 times in your first 10 occurrences; in your last 10, 2." */
export function recentSentence(name: string | null, first: WireRecent | null | undefined, last: WireRecent | null | undefined): string | null {
  if (!first || !last || first.n <= 0 || last.n <= 0) return null;
  const about = name ? ` with ${name}` : "";
  return `You needed help${about} ${timesWord(first.assisted)} in your first ${first.n} occurrences; in your last ${last.n}, ${last.assisted}.`;
}

export function baselineLine(w: WireGrowth): string | null {
  const b = w.baseline;
  const ind = w.components.independence;
  if (!b || !ind) return null;
  return `In your first ${b.n} occurrences you finished ${b.k} without a cue. In the latest ${ind.n}, ${ind.k}.`;
}

/* -- The Fade: what cue weight the worker actually saw ----------------------------------------- */
export interface CueWeight {
  n: number;
  /** Share of the window's occurrences that got any cue (0 to 1). */
  cuedShare: number;
  /** Mean tier (1 to 4) among occurrences that got a cue; null when none did. */
  meanTier: number | null;
  /** Share of cued occurrences that carried a text chip (tier 2 or above). */
  chipShare: number | null;
}

export function cueWeight(tiers: number[] | undefined): CueWeight | null {
  if (!tiers || tiers.length < 2) return null;
  const n = tiers.reduce((a, b) => a + b, 0);
  if (n <= 0) return null;
  const cued = n - (tiers[0] ?? 0);
  if (cued <= 0) return { n, cuedShare: 0, meanTier: null, chipShare: null };
  let sum = 0;
  for (let k = 1; k < tiers.length; k++) sum += k * (tiers[k] ?? 0);
  const chips = tiers.slice(2).reduce((a, b) => a + b, 0);
  return { n, cuedShare: cued / n, meanTier: sum / cued, chipShare: chips / cued };
}

export interface Glyph {
  /** No cue at all in the window: a dot, not a ring. */
  none: boolean;
  /** Ring stroke width in px: heavier cues draw a heavier ring (tier 1 thin, tier 4 thick). */
  stroke: number;
  /** Ring opacity: fewer cued occurrences draw a fainter ring. */
  opacity: number;
  /** A small bar under the ring when most cues carried a text chip. */
  chip: boolean;
}

export function glyphOf(w: CueWeight | null): Glyph | null {
  if (!w) return null;
  if (w.cuedShare <= 0 || w.meanTier == null) return { none: true, stroke: 0, opacity: 1, chip: false };
  return {
    none: false,
    stroke: 0.75 + (Math.min(4, Math.max(1, w.meanTier)) - 1) * 0.85,
    opacity: 0.22 + 0.78 * Math.min(1, w.cuedShare),
    chip: (w.chipShare ?? 0) >= 0.5,
  };
}

/** Pick indices of `xs` (pixel positions, ascending) at least `minGap` apart, always keeping the last one. */
export function pickSamples(xs: number[], minGap: number): number[] {
  const out: number[] = [];
  let at = Infinity;
  for (let i = xs.length - 1; i >= 0; i--) {
    if (at - xs[i] >= minGap || out.length === 0) { out.push(i); at = xs[i]; }
  }
  return out.reverse();
}

/* -- The curve --------------------------------------------------------------------------------- */
export interface CurvePoint {
  i: number;
  t: string;
  p: number;
  lo: number;
  hi: number;
  n: number;
  /** The help level the engine reported at this occurrence (1 to 4). */
  level: number | null;
  /** What the strip draws: for one skill the level itself, for everything the mean level over the window (the skills differ, so one occurrence's level would jump about). */
  lv: number | null;
  cue: CueWeight | null;
}

/** Mean of the non-null levels in a trailing window of `size` points (the point and the ones before it). */
export function trailingMean(levels: (number | null)[], size: number): (number | null)[] {
  return levels.map((_, k) => {
    const seg = levels.slice(Math.max(0, k - size + 1), k + 1).filter((v): v is number => v != null);
    return seg.length ? seg.reduce((a, b) => a + b, 0) / seg.length : null;
  });
}

export function curveOf(c: WireCurvePoint[], opts: { smoothLevel?: boolean; window?: number } = {}): CurvePoint[] {
  const means = opts.smoothLevel ? trailingMean(c.map((p) => p.level), opts.window ?? DEFAULT_WINDOW) : null;
  return c.map((p, k) => ({ i: p.i, t: p.t_hour, p: p.independence, lo: p.lo, hi: p.hi, n: p.n, level: p.level, lv: means ? means[k] : p.level, cue: cueWeight(p.tiers) }));
}

const LEVEL_NAME = ["", "full", "small", "dot", "gone"];
export const levelName = (l: number) => LEVEL_NAME[Math.min(4, Math.max(1, Math.round(l)))];

export function pointReadout(p: CurvePoint, window: number, levelPct = 95, smoothLevel = false): string {
  const lvl = p.lv == null ? "" : smoothLevel ? ` Help level about L${p.lv.toFixed(1)} on average (L1 full, L4 gone).` : ` Help level L${Math.round(p.lv)} (${levelName(p.lv)}).`;
  const part = p.n < window ? ` Only ${p.n} occurrences so far, so the band is wide.` : "";
  const cue = p.cue
    ? p.cue.cuedShare <= 0 ? " No cue shown." : ` A cue was shown in ${pct(p.cue.cuedShare)} of them, mean tier ${p.cue.meanTier?.toFixed(1)}.`
    : "";
  return `Occurrence ${p.i} (${fmtDay(p.t)}): ${pct(p.p)} finished with no cue accepted, ${levelPct}% interval ${pctRange([p.lo, p.hi])}, n ${p.n}.${lvl}${cue}${part}`;
}

/* -- Components in plain words ----------------------------------------------------------------- */
export interface ComponentCard {
  id: "help" | "time" | "keep";
  title: string;
  /** What is measured, in one line. */
  measure: string;
  /** Big figure; "Not yet" when the value cannot be computed. */
  display: string;
  value: number | null;
  ci: Interval | null;
  scale: [number, number];
  /** The fact, from the counts. */
  sentence: string;
  /** When value is null: what is missing and when it will appear. */
  pending: string | null;
}

function retentionCard(r: WireRetention | null | undefined): ComponentCard {
  const base = { id: "keep" as const, title: "Keeps it after a few days", measure: `Finished with no cue on the first occurrence ${RETENTION_DAYS} or more days after you were taught the step.`, scale: [0, 1] as [number, number] };
  if (!r || r.value == null) {
    return { ...base, display: "Not yet", value: null, ci: null, sentence: "", pending: `This appears once a step comes up again ${RETENTION_DAYS} or more days after you were taught it. It is blank until then, not zero.` };
  }
  return { ...base, display: pct(r.value), value: r.value, ci: r.wilson, sentence: `Unaided on ${r.k} of ${r.n} steps that came back after ${RETENTION_DAYS} or more days.`, pending: null };
}

export function cardsOf(w: WireGrowth): ComponentCard[] {
  const ind = w.components.independence;
  const help: ComponentCard = {
    id: "help",
    title: "Needs help less often",
    measure: `Share of your latest ${ind?.n ?? w.window} occurrences that finished with no cue accepted.`,
    display: ind ? pct(ind.share) : "Not yet",
    value: ind?.share ?? null,
    ci: ind?.wilson ?? null,
    scale: [0, 1],
    sentence: ind ? `${ind.k} of ${ind.n} finished with no cue accepted${w.baseline ? `; in your first ${w.baseline.n}, ${w.baseline.k}` : ""}.` : "",
    pending: ind ? null : "This appears once there are enough occurrences.",
  };
  const g = w.components.gap_closure;
  const lo = g?.ci ? Math.min(0, g.ci[0]) : 0;
  const time: ComponentCard = {
    id: "time",
    title: "Recovers faster",
    measure: "Seconds lost against the expert's median on the same step, now compared with your first 5 occurrences.",
    display: g?.value != null ? pct(g.value) : "Not yet",
    value: g?.value ?? null,
    ci: g?.ci ?? null,
    scale: [lo, 1],
    sentence: g && g.value != null && g.first5_lost_s != null && g.last5_lost_s != null
      ? `You lost ${Math.round(g.first5_lost_s)} s per step in your first ${g.n_first} occurrences and ${Math.round(g.last5_lost_s)} s in your last ${g.n_last}. ${g.value >= 0 ? "That is the share of the gap won back." : "That is more time lost than at the start."}`
      : "",
    pending: g && g.value != null ? null : "This appears once there are enough occurrences to compare with your first 5.",
  };
  return [help, time, retentionCard(w.components.retention)];
}

/* -- The composite, always with its parts ------------------------------------------------------ */
export interface CompositePart { id: string; label: string; weight: number; value: number | null; shown: string }
export interface CompositeView {
  /** Always true: the composite overstated improvement on simulated learners whose skill did not change. */
  experimental: true;
  caveat: string;
  value: number;
  ci: Interval | null;
  partial: boolean;
  availableWeight: number;
  parts: CompositePart[];
  note: string;
}

export function compositeOf(w: WireGrowth): CompositeView | null {
  const s = w.score;
  if (s.composite == null) return null;
  const wts = s.composite_partial && s.used_weights ? s.used_weights : s.weights;
  const c = w.components;
  const parts: CompositePart[] = [
    { id: "ind", label: "Independence, lower bound", weight: wts.independence_lb ?? 0, value: c.independence?.lower ?? c.independence?.wilson?.[0] ?? null, shown: "" },
    { id: "mas", label: "Mastery, with forgetting", weight: wts.mastery ?? 0, value: c.mastery?.value ?? null, shown: "" },
    { id: "gap", label: "Time lost, won back", weight: wts.gap_closure ?? 0, value: c.gap_closure?.value ?? null, shown: "" },
    { id: "ret", label: "Kept after days", weight: wts.retention ?? 0, value: c.retention?.value ?? null, shown: "" },
  ].map((p) => ({ ...p, shown: p.value == null ? "not yet" : pct(p.value) }));
  const note = s.composite_partial
    ? `Not every part exists yet, so the score uses the parts that do (${pct(s.available_weight)} of the weight, re-weighted to 100%).`
    : "All four parts are in.";
  return {
    experimental: true,
    caveat: s.composite_caveat || "Experimental. Read the trend and the independence interval instead.",
    value: s.composite, ci: s.composite_ci, partial: s.composite_partial, availableWeight: s.available_weight, parts, note,
  };
}

/* -- Skill rows -------------------------------------------------------------------------------- */
export interface TtpView { median: number; ci: Interval | null; n: number }
export interface SkillRowView {
  id: string;
  name: string;
  label: string;
  n: number;
  independent: number;
  assisted: number;
  other: number;
  unaidedShare: number;
  level: number | null;
  direction: Direction;
  retrievalDue: boolean;
  ttp: TtpView | null;
  retention: { text: string; value: number | null; n: number } | null;
  recent: string | null;
}

const ttpOf = (m: WireMedian | null | undefined): TtpView | null => (m && m.median_s != null && m.n > 0 ? { median: m.median_s, ci: m.ci, n: m.n } : null);

export function skillRows(by: WireSkill[]): SkillRowView[] {
  return by.map((s) => {
    const other = Math.max(0, s.n - s.independent - s.assisted);
    return {
      id: s.skill,
      name: s.name || s.label || humanise(s.skill),
      label: s.label || humanise(s.skill),
      n: s.n,
      independent: s.independent,
      assisted: s.assisted,
      other,
      unaidedShare: s.n > 0 ? s.independent / s.n : 0,
      level: s.level,
      direction: s.direction,
      retrievalDue: !!s.retrieval_due,
      ttp: ttpOf(s.time_to_progress?.after_cue),
      retention: s.retention ? { text: s.retention.value == null ? "not yet" : `${pct(s.retention.value)} of ${s.retention.n}`, value: s.retention.value, n: s.retention.n } : null,
      recent: recentSentence(s.name || s.label, s.first10, s.last10),
    };
  });
}

/** "check-the-cliff" -> "Check the cliff": only used if the engine sends neither name nor label. */
export function humanise(id: string): string {
  const s = id.replace(/[-_]+/g, " ").trim();
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : id;
}

/** "Needs less help on 3 of 5 skills." Counted from the rows, so it always agrees with them. The rest are "cannot tell yet", never "no change". */
export function claimOf(rows: SkillRowView[]): string {
  if (!rows.length) return "";
  const judged = rows.filter((r) => r.direction !== "too_early");
  if (!judged.length) return "Too early to say for any skill.";
  const less = judged.filter((r) => r.direction === "less_help").length;
  const more = judged.filter((r) => r.direction === "more_help").length;
  const rest = rows.length - less - more;
  const parts = [`Needs less help on ${less} of ${plural(rows.length, "skill")}`];
  if (more) parts.push(`more help on ${more}`);
  const head = parts.join("; ");
  return `${head}. ${rest > 0 ? `For ${rest === rows.length ? "all of them" : `the other ${rest}`}, it cannot tell yet. ` : ""}This is not a measure of expertise.`;
}

/* -- Origin wording ---------------------------------------------------------------------------- */
export function originSentence(detail: OriginDetail | undefined, origin: "real" | "synthetic" | "mixed" | undefined): string {
  if (detail === "simulated_participants") return "Simulated participants (language model), not people.";
  if (detail === "synthetic_learner") return "Synthetic learners with planted learning curves, not people.";
  if (detail === "live_worker") return "Your own work on this computer. One person is not a study.";
  if (origin === "synthetic") return "Synthetic data, not people.";
  if (origin === "real") return "Real work. One person is not a study.";
  return "";
}

/* -- Offloaded work ---------------------------------------------------------------------------- */
export interface OffloadItem { id: string; when: string; stream: "delegated" | "automation"; streamWord: string; what: string; outcome: string; minutes: number | null }

export const OUTCOME_WORD: Record<LedgerRow["outcome"], string> = { clean: "done", assisted: "needed you", error: "failed", abandoned: "stopped" };
/** What happened to a run the agent did for the person. */
export const OFFLOAD_WORD: Record<NonNullable<LedgerRow["offload_outcome"]>, string> = { done: "done", queued: "waiting for your approval", failed: "failed", yielded: "paused for you" };

export function offloadItems(rows: LedgerRow[], labelOf: (skill: string) => string, limit = 8): OffloadItem[] {
  return rows
    .filter((r) => r.stream === "delegated" || r.stream === "automation")
    .sort((a, b) => (a.t_hour < b.t_hour ? 1 : a.t_hour > b.t_hour ? -1 : 0))
    .slice(0, limit)
    .map((r) => ({
      id: r.id,
      when: fmtDayHour(r.t_hour),
      stream: r.stream as "delegated" | "automation",
      streamWord: r.stream === "delegated" ? "You asked" : "Overnight",
      what: r.skill ? labelOf(r.skill) : r.routine ? humanise(r.routine) : "A run",
      outcome: r.offload_outcome ? OFFLOAD_WORD[r.offload_outcome] ?? r.offload_outcome : OUTCOME_WORD[r.outcome] ?? r.outcome,
      minutes: r.minutes != null && r.minutes > 0 ? r.minutes : null,
    }));
}

/* -- Ledger controls --------------------------------------------------------------------------- */
export interface LedgerCounts { assist: number; delegated: number; automation: number }

export function countsOf(w: WireGrowth, fromLedger?: Partial<LedgerCounts> | null): LedgerCounts {
  const c = fromLedger ?? w.counts;
  return {
    assist: c?.assist ?? w.occurrences.total,
    delegated: c?.delegated ?? w.offloaded.delegated,
    automation: c?.automation ?? w.offloaded.automation,
  };
}

export const totalRows = (c: LedgerCounts) => c.assist + c.delegated + c.automation;

/** What deleting does, in the words the worker sees. The engine states the same list (CUE-ENGINE, 7 Nov). */
export function deleteCopy(c: LedgerCounts, example: boolean): { what: string; kept: string; button: string } {
  const total = totalRows(c);
  const what = `This deletes ${plural(total, "row")} from the ledger on this computer (${c.assist} assist, ${c.delegated} delegated, ${c.automation} overnight), the answers you gave to Cue's questions, and the one-line summary in your memory file's Skill state section. It adds one line to the audit log with counts only. Your curve is worked out from the ledger, so it starts again from nothing.`;
  const kept = example
    ? "These rows are example data, so clearing them only changes this screen."
    : "Nothing else is touched: your memory file's other lines, routines, queue and settings stay as they are.";
  return { what, kept, button: `Delete ${plural(total, "row")}` };
}

export function deletedCount(r: { deleted: number | { assist?: number; delegated?: number; automation?: number } }): number {
  if (typeof r.deleted === "number") return r.deleted;
  const d = r.deleted ?? {};
  return (d.assist ?? 0) + (d.delegated ?? 0) + (d.automation ?? 0);
}

/** Field names across the rows (a delegated row has a few more than an assist row), so the page can say exactly what is stored. */
export function ledgerFields(rows: LedgerRow[]): string[] {
  const out: string[] = [];
  for (const r of rows) for (const k of Object.keys(r)) if (!out.includes(k)) out.push(k);
  return out;
}

/* -- Early state: the raw occurrences, no estimate claimed ------------------------------------- */
export interface Mark { unaided: boolean; skill: string | null }
export function marksOf(rows: LedgerRow[], skill: string | null): Mark[] {
  return rows
    .filter((r) => r.stream === "assist" && (!skill || r.skill === skill))
    .sort((a, b) => (a.t_hour < b.t_hour ? -1 : a.t_hour > b.t_hour ? 1 : a.id < b.id ? -1 : 1))
    .map((r) => ({ unaided: r.outcome === "clean", skill: r.skill }));
}

/** How many more occurrences until the curve starts. */
export const remainingUntil = (total: number, needed: number) => Math.max(0, needed - total);

/* -- The whole screen's model ------------------------------------------------------------------- */
export interface GrowthView {
  status: Status;
  focusId: string;
  focusName: string | null;
  total: number;
  needed: number;
  window: number;
  levelPct: number;
  curve: CurvePoint[];
  baseline: WireGrowth["baseline"];
  title: string;
  lede: string;
  recentLine: string | null;
  trend: { direction: Direction; sentence: string; per10: number | null; ci: Interval | null; stillNeeded: number };
  /** Independence now: the headline figure beside the trend. */
  independence: { share: number; ci: Interval; k: number; n: number } | null;
  composite: CompositeView | null;
  cards: ComponentCard[];
  skills: SkillRowView[];
  claim: string;
  offloaded: { delegated: number; automation: number };
  hasCueWeights: boolean;
  /** True when the fade's level line is a mean over the window (everything), false when it is one skill's own level. */
  smoothLevel: boolean;
  /** Minutes of work done for the worker, by stream, when the engine reports them. */
  offloadedMinutes: { delegated: number; automation: number };
  weights: WireGrowth["score"]["weights"];
  weightsNote: string;
  originDetail: OriginDetail | undefined;
}

export function buildView(w: WireGrowth, levelPct = 95): GrowthView {
  const status = statusOf(w);
  const skills = skillRows(w.by_skill ?? []);
  const focus = w.skill ? skills.find((s) => s.id === w.skill) ?? null : null;
  const focusName = w.skill ? (focus?.name ?? humanise(w.skill)) : null;
  const smoothLevel = !w.skill;
  const curve = status === "ready" ? curveOf(w.curve, { smoothLevel, window: w.window || DEFAULT_WINDOW }) : [];
  const direction: Direction = status === "ready" ? w.trend.direction : "too_early";
  const imp = improvement(w.trend);
  return {
    status,
    focusId: w.skill ?? "overall",
    focusName,
    total: w.readiness?.occurrences ?? w.occurrences.total,
    needed: w.readiness?.needed ?? DEFAULT_NEEDED,
    window: w.window || DEFAULT_WINDOW,
    levelPct,
    curve,
    baseline: w.baseline,
    title: heroTitle(status, direction, focusName),
    lede: status === "ready" ? baselineLine(w) ?? "" : "",
    recentLine: focus?.recent ?? null,
    trend: { direction, sentence: trendSentence({ ...w.trend, direction }, levelPct, stillNeeded({ readiness: w.readiness, trend: { ...w.trend, direction } }), w.readiness.trend_needed ?? null, w.readiness.occurrences), per10: imp.per10, ci: imp.ci, stillNeeded: stillNeeded({ readiness: w.readiness, trend: { ...w.trend, direction } }) },
    independence: w.components.independence ? { share: w.components.independence.share, ci: w.components.independence.wilson, k: w.components.independence.k, n: w.components.independence.n } : null,
    composite: status === "ready" ? compositeOf(w) : null,
    cards: cardsOf(w),
    skills,
    claim: w.claim || claimOf(skills),
    offloaded: { delegated: w.offloaded.delegated, automation: w.offloaded.automation },
    hasCueWeights: curve.some((p) => p.cue != null),
    smoothLevel,
    offloadedMinutes: { delegated: w.offloaded.minutes?.delegated ?? 0, automation: w.offloaded.minutes?.automation ?? 0 },
    weights: w.score.weights,
    weightsNote: w.score.weights_note,
    originDetail: w.origin_detail,
  };
}

/* -- What this does not show ------------------------------------------------------------------- */
export function limitations(v: Pick<GrowthView, "needed" | "window" | "levelPct" | "weights"> & { caveat?: string | null }, origin: "real" | "synthetic" | "mixed" | undefined): string[] {
  const w = v.weights;
  const out = [
    `Fewer than ${v.needed} occurrences is too few to draw a curve, so until then you see counts only. Even after that, a window of ${v.window} gives a wide ${v.levelPct}% interval.`,
    "An occurrence counts only when the step really came up in your work. A step that did not come up is not counted.",
    "A step is independent only if you finished it without accepting a cue. Dismissing a cue and not finishing is not independence, and an error counts against you.",
    "Needing less help is not the same as being expert. This cannot tell whether the work is right, or whether you know why.",
    "This does not show that the cues caused the change. You may have been learning on your own, or the work may have got easier. There is no comparison group here.",
    `Keeping a skill is only measured when a step comes back ${RETENTION_DAYS} or more days after you were taught it. Until then it is blank, not zero.`,
    "Work you hand to the agent, and automations that ran overnight, are never counted. Handing work off cannot raise this score.",
    `The composite is experimental. Its weights (${Math.round(w.independence_lb * 100)}, ${Math.round(w.mastery * 100)}, ${Math.round(w.gap_closure * 100)} and ${Math.round(w.retention * 100)} percent) are stated assumptions, not fitted to data, and on simulated learners it could rise when their skill had not changed. Read the trend and the independence interval first.`,
    "A trend whose interval includes zero is not evidence of no change. At this many occurrences a real improvement is often missed, so the page says it cannot tell yet.",
  ];
  if (v.caveat) out.push(v.caveat);
  if (origin !== "real") out.push("These numbers come from invented learners or simulated participants with planted learning curves. They test that the method recovers what was planted. The live study, with 4 teammates, has not been run.");
  else out.push("This is one person's own work. One person is not a study.");
  return out;
}
