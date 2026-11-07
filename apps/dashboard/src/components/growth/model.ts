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

export function trendSentence(trend: WireGrowth["trend"], levelPct = 95): string {
  const { per10, ci } = improvement(trend);
  if (trend.direction === "too_early" || per10 == null || !ci) return "Too early for a trend.";
  const a = Math.abs(per10).toFixed(Math.abs(per10) < 10 ? 1 : 0);
  const range = `${levelPct}% interval ${pts(ci[0])} to ${pts(ci[1])} points`;
  if (trend.direction === "less_help") return `About ${a} points more of your occurrences finish with no cue for every 10 more (${range}).`;
  if (trend.direction === "more_help") return `About ${a} points fewer of your occurrences finish with no cue for every 10 more (${range}).`;
  return `No clear change: the ${levelPct}% interval runs from ${pts(ci[0])} to ${pts(ci[1])} points per 10 occurrences, and that includes zero.`;
}

export const DIRECTION_WORD: Record<Direction, string> = {
  less_help: "needs less help",
  steady: "levelled off",
  more_help: "needs more help",
  too_early: "too early to say",
};

export function heroTitle(status: Status, direction: Direction, name: string | null): string {
  if (status === "empty") return "Nothing to show yet";
  if (status === "early" || direction === "too_early") return name ? `Too early to say how much help you need with ${name}` : "Too early to say how much help you need";
  if (direction === "less_help") return name ? `You need less help with ${name}` : "You need help less often than you did";
  if (direction === "more_help") return name ? `You have needed more help with ${name} lately` : "You have needed more help lately";
  return name ? `Your need for help with ${name} has levelled off` : "Your need for help has levelled off";
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
  level: number | null;
  cue: CueWeight | null;
}

export const curveOf = (c: WireCurvePoint[]): CurvePoint[] =>
  c.map((p) => ({ i: p.i, t: p.t_hour, p: p.independence, lo: p.lo, hi: p.hi, n: p.n, level: p.level, cue: cueWeight(p.tiers) }));

export function pointReadout(p: CurvePoint, window: number, levelPct = 95): string {
  const lvl = p.level != null ? ` Help level L${p.level}.` : "";
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
    { id: "ind", label: "Independence, lower bound", weight: wts.independence_lb, value: c.independence?.lower ?? c.independence?.wilson?.[0] ?? null, shown: "" },
    { id: "mas", label: "Mastery, with forgetting", weight: wts.mastery, value: c.mastery?.value ?? null, shown: "" },
    { id: "gap", label: "Time lost, won back", weight: wts.gap_closure, value: c.gap_closure?.value ?? null, shown: "" },
    { id: "ret", label: "Kept after days", weight: wts.retention, value: c.retention?.value ?? null, shown: "" },
  ].map((p) => ({ ...p, shown: p.value == null ? "not yet" : pct(p.value) }));
  const note = s.composite_partial
    ? `Not every part exists yet, so the score uses the parts that do (${pct(s.available_weight)} of the weight, re-weighted to 100%).`
    : "All four parts are in.";
  return { value: s.composite, ci: s.composite_ci, partial: s.composite_partial, availableWeight: s.available_weight, parts, note };
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

/** "Needs less help on 3 of 5 skills." Counted from the rows, so it always agrees with them. */
export function claimOf(rows: SkillRowView[]): string {
  const judged = rows.filter((r) => r.direction !== "too_early");
  if (!rows.length) return "";
  if (!judged.length) return "Too early to say for any skill.";
  const less = judged.filter((r) => r.direction === "less_help").length;
  return `Needs less help on ${less} of ${plural(judged.length, "skill")}${judged.length < rows.length ? ` (${rows.length - judged.length} still too early)` : ""}. This is not a measure of expertise.`;
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
export interface OffloadItem { id: string; when: string; stream: "delegated" | "automation"; streamWord: string; skill: string; outcome: string }

export const OUTCOME_WORD: Record<LedgerRow["outcome"], string> = { clean: "done", assisted: "needed you", error: "failed", abandoned: "stopped" };

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
      skill: labelOf(r.skill),
      outcome: OUTCOME_WORD[r.outcome] ?? r.outcome,
    }));
}

/* -- Ledger controls --------------------------------------------------------------------------- */
export interface LedgerCounts { assist: number; delegated: number; automation: number }

export function countsOf(w: WireGrowth, fromLedger?: LedgerCounts | null): LedgerCounts {
  return fromLedger ?? { assist: w.occurrences.total, delegated: w.offloaded.delegated, automation: w.offloaded.automation };
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

/** Field names of a ledger row, so the page can say exactly what is stored. */
export function ledgerFields(rows: LedgerRow[]): string[] {
  return rows.length ? Object.keys(rows[0]) : [];
}

/* -- Early state: the raw occurrences, no estimate claimed ------------------------------------- */
export interface Mark { unaided: boolean; skill: string }
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
  trend: { direction: Direction; sentence: string; per10: number | null; ci: Interval | null };
  composite: CompositeView | null;
  cards: ComponentCard[];
  skills: SkillRowView[];
  claim: string;
  offloaded: { delegated: number; automation: number };
  hasCueWeights: boolean;
  weights: WireGrowth["score"]["weights"];
  weightsNote: string;
  originDetail: OriginDetail | undefined;
}

export function buildView(w: WireGrowth, levelPct = 95): GrowthView {
  const status = statusOf(w);
  const skills = skillRows(w.by_skill ?? []);
  const focus = w.skill ? skills.find((s) => s.id === w.skill) ?? null : null;
  const focusName = w.skill ? (focus?.name ?? humanise(w.skill)) : null;
  const curve = status === "ready" ? curveOf(w.curve) : [];
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
    trend: { direction, sentence: trendSentence({ ...w.trend, direction }, levelPct), per10: imp.per10, ci: imp.ci },
    composite: status === "ready" ? compositeOf(w) : null,
    cards: cardsOf(w),
    skills,
    claim: claimOf(skills),
    offloaded: { delegated: w.offloaded.delegated, automation: w.offloaded.automation },
    hasCueWeights: curve.some((p) => p.cue != null),
    weights: w.score.weights,
    weightsNote: w.score.weights_note,
    originDetail: w.origin_detail,
  };
}

/* -- What this does not show ------------------------------------------------------------------- */
export function limitations(v: Pick<GrowthView, "needed" | "window" | "levelPct" | "weights">, origin: "real" | "synthetic" | "mixed" | undefined): string[] {
  const w = v.weights;
  const out = [
    `Fewer than ${v.needed} occurrences is too few to draw a curve, so until then you see counts only. Even after that, a window of ${v.window} gives a wide ${v.levelPct}% interval.`,
    "An occurrence counts only when the step really came up in your work. A step that did not come up is not counted.",
    "A step is independent only if you finished it without accepting a cue. Dismissing a cue and not finishing is not independence, and an error counts against you.",
    "Needing less help is not the same as being expert. This cannot tell whether the work is right, or whether you know why.",
    "This does not show that the cues caused the change. You may have been learning on your own, or the work may have got easier. There is no comparison group here.",
    `Keeping a skill is only measured when a step comes back ${RETENTION_DAYS} or more days after you were taught it. Until then it is blank, not zero.`,
    "Work you hand to the agent, and automations that ran overnight, are never counted. Handing work off cannot raise this score.",
    `The composite's weights (${Math.round(w.independence_lb * 100)}, ${Math.round(w.mastery * 100)}, ${Math.round(w.gap_closure * 100)} and ${Math.round(w.retention * 100)} percent) are stated assumptions, not fitted to data.`,
  ];
  if (origin !== "real") out.push("These numbers come from invented learners or simulated participants with planted learning curves. They test that the method recovers what was planted. The live study, with 4 teammates, has not been run.");
  else out.push("This is one person's own work. One person is not a study.");
  return out;
}
