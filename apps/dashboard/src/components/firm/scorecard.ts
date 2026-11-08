// The prediction scorecard: our stuck forecasts against what happened. Pure logic, no React and no network, so it is tested.
//
// It reads `evals/report.json` (through GET /eval/report) in two shapes:
//  - `sections.hazard`  (v1): model and baselines with intervals, calibration bins whose `lo`/`hi` are BIN EDGES (not an interval),
//    false alarms per hour, detection rate, a budget.
//  - `sections.mlv2.scorecard` (ML2, additive): the frozen v2 candidate, v1 and the baselines on the same pool, an `accepted` flag.
// Rules this file keeps: it never invents an interval (an estimate with no interval says so); the only interval it computes is a
// Wilson interval for a bin's observed share, from that bin's own count; v1 stays the default until ML2 says accepted; the
// candidate is never mixed onto an axis with numbers from a different pool.
import type { Est, Interval } from "./wire";

export type { Est, Interval };

/** A bin with fewer cases than this is drawn hollow and labelled thin. A design choice, printed in the key. */
export const THIN_N = 30;
/** "Close to what happened" means within this many points of the diagonal. A design choice, printed in the key. */
export const CLOSE_POINTS = 0.05;

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => !!v && typeof v === "object" && !Array.isArray(v);
const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const str = (v: unknown): string | null => (typeof v === "string" && v.trim() ? v.trim() : null);
const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);

/* -- Reading estimates -------------------------------------------------------------------------- */

/** `[lo, hi]`, `{lo, hi}`, `{low, high}`: a proper pair or null. Swapped ends are put right; nothing is made up. */
export function pair(v: unknown): Interval | null {
  let lo: unknown, hi: unknown;
  if (Array.isArray(v) && v.length === 2) [lo, hi] = v;
  else if (isObj(v)) { lo = v.lo ?? v.low ?? v.lower; hi = v.hi ?? v.high ?? v.upper; }
  if (!isNum(lo) || !isNum(hi)) return null;
  return lo <= hi ? [lo, hi] : [hi, lo];
}

/** One estimate from a bare number, `{value, ci}`, `{value, interval}` or `{point, lo, hi}`. The interval is null when there is none. */
export function estOf(v: unknown): Est | null {
  if (isNum(v)) return { value: v, ci: null };
  if (!isObj(v)) return null;
  const value = [v.value, v.point, v.mean, v.estimate, v.share].find(isNum);
  if (value === undefined) return null;
  const ci = pair(v.ci ?? v.interval ?? v.wilson) ?? (isNum(v.lo) && isNum(v.hi) ? pair([v.lo, v.hi]) : null);
  return { value: value as number, ci };
}

/** `obj[key]` as an estimate, with the interval taken from a sibling key (`<key>_ci`, `ci_<key>`, `<key>_interval`) when the value is bare. */
export function estFrom(obj: unknown, key: string): Est | null {
  if (!isObj(obj)) return null;
  const e = estOf(obj[key]);
  if (!e) return null;
  if (e.ci) return e;
  return { value: e.value, ci: pair(obj[`${key}_ci`] ?? obj[`ci_${key}`] ?? obj[`${key}_interval`]) };
}

/* -- Wilson interval --------------------------------------------------------------------------- */

/**
 * Wilson score interval for an observed share `p` over `n` cases (z = 1.96 for 95%). Null when there are no cases.
 * Bins are treated as independent, so this is narrower than the person-level uncertainty: the footer says so.
 */
export function wilson(p: number, n: number, z = 1.96): Interval | null {
  if (!isNum(p) || !isNum(n) || n <= 0) return null;
  const q = Math.min(1, Math.max(0, p));
  const z2 = z * z;
  const centre = q + z2 / (2 * n);
  const margin = z * Math.sqrt((q * (1 - q)) / n + z2 / (4 * n * n));
  const d = 1 + z2 / n;
  return [Math.max(0, (centre - margin) / d), Math.min(1, (centre + margin) / d)];
}

/* -- Calibration bins -------------------------------------------------------------------------- */

export interface Bin {
  /** Mean forecast in the bin (x). */
  p: number;
  /** Share of cases where someone really was stuck (y). */
  freq: number;
  n: number;
  /** Interval on `freq`. Null when the bin has no count. */
  ci: Interval | null;
  /** Fewer than THIN_N cases. */
  thin: boolean;
  /** The bin's own edges, when the report gives them (v1 does). */
  edge: Interval | null;
}

/**
 * `intervalGiven` is true when the report's `lo`/`hi` are an interval on the observed share (ML2's block). In v1 they are the edges of the
 * forecast band, so they are NOT used as an interval; a Wilson interval is computed from the count instead.
 */
export function readBins(raw: unknown, intervalGiven: boolean): Bin[] {
  const out: Bin[] = [];
  for (const b of arr(raw)) {
    if (!isObj(b)) continue;
    const p = [b.p_mean, b.p, b.pred].find(isNum);
    const freq = [b.freq, b.observed, b.obs].find(isNum);
    const n = isNum(b.n) ? b.n : 0;
    if (p === undefined || freq === undefined || n <= 0) continue;
    const own = intervalGiven ? pair([b.lo, b.hi]) : pair(b.ci);
    const ci = own && own[0] <= freq && freq <= own[1] ? own : wilson(freq, n);
    const edge = !intervalGiven ? pair([b.lo, b.hi]) : null;
    out.push({ p: p as number, freq: freq as number, n, ci, thin: n < THIN_N, edge });
  }
  return out.sort((a, b) => a.p - b.p);
}

export type Gap = "close" | "runs_high" | "runs_low";
/** Forecast against what happened: high means the forecast said stuck more often than it happened. */
export function gapOf(b: Pick<Bin, "p" | "freq">): Gap {
  const d = b.freq - b.p;
  // A hair of slack so 0.5 against 0.55 is not pushed out of "close" by floating-point noise.
  return Math.abs(d) <= CLOSE_POINTS + 1e-9 ? "close" : d < 0 ? "runs_high" : "runs_low";
}

export interface ReliabilitySummary {
  total: number;
  thin: number;
  reliable: number;
  close: number;
  /** The lowest forecast above which every bin that has enough cases runs high (or low), or null. */
  highFrom: number | null;
  lowFrom: number | null;
}

export function summariseBins(bins: Bin[]): ReliabilitySummary {
  const reliable = bins.filter((b) => !b.thin);
  const high = reliable.filter((b) => gapOf(b) === "runs_high");
  const low = reliable.filter((b) => gapOf(b) === "runs_low");
  return {
    total: bins.length, thin: bins.length - reliable.length, reliable: reliable.length,
    close: reliable.filter((b) => gapOf(b) === "close").length,
    highFrom: high.length ? Math.min(...high.map((b) => b.p)) : null,
    lowFrom: low.length ? Math.min(...low.map((b) => b.p)) : null,
  };
}

const pc = (x: number): string => `${Math.round(x * 100)}%`;

/** The one plain claim above the diagram, built from the bins: what is close, and where the forecast runs high or low. */
export function reliabilityLine(s: ReliabilitySummary): string {
  if (s.total === 0) return "There are no forecast bins to draw.";
  if (s.reliable === 0) return `Every bin has fewer than ${THIN_N} cases, so none can be read yet.`;
  const lead = s.close === s.reliable
    ? `In every band with ${THIN_N} or more cases, the forecast is within ${Math.round(CLOSE_POINTS * 100)} points of what happened.`
    : `In ${s.close} of ${s.reliable} bands with ${THIN_N} or more cases, the forecast is within ${Math.round(CLOSE_POINTS * 100)} points of what happened.`;
  const tail: string[] = [];
  if (s.highFrom !== null) tail.push(`From about ${pc(s.highFrom)} up it runs high: it says stuck more often than it happened.`);
  if (s.lowFrom !== null) tail.push(`From about ${pc(s.lowFrom)} it runs low.`);
  return [lead, ...tail].join(" ");
}

/** The sentence for one bin, for the keyboard readout. */
export function binReadout(b: Bin, levelPct: number): string {
  const iv = b.ci ? ` (${levelPct}% interval ${pc(b.ci[0])} to ${pc(b.ci[1])})` : " (no interval)";
  const g = gapOf(b);
  const verdict = g === "close" ? "Close to the forecast." : g === "runs_high" ? "The forecast runs high here." : "The forecast runs low here.";
  const thin = b.thin ? ` Only ${b.n} cases, so do not read much into this band.` : "";
  return `Forecast about ${pc(b.p)}. Someone was stuck in ${pc(b.freq)} of ${b.n.toLocaleString("en-GB")} cases${iv}. ${verdict}${thin}`;
}

/* -- Comparisons ------------------------------------------------------------------------------- */

export interface Relation {
  /** Is `a` lower than `b`, by the point estimates? Null when either is missing. */
  lower: boolean | null;
  /** Do the intervals leave a clear gap between them? Null when either interval is missing: then it cannot be said. */
  clear: boolean | null;
}

/** For measures where lower is better (log loss, Brier). */
export function relate(a: Est | null, b: Est | null): Relation {
  if (!a || !b) return { lower: null, clear: null };
  const lower = a.value < b.value;
  if (!a.ci || !b.ci) return { lower, clear: null };
  const clear = a.ci[1] < b.ci[0] || b.ci[1] < a.ci[0];
  return { lower, clear };
}

export type RowId = "ours" | "candidate" | "v1" | "base_rate" | "time_since_progress";
export interface Row { id: RowId; label: string; est: Est | null; ours?: boolean; tag?: string | null }
export interface MetricPanel { key: "log_loss" | "brier"; title: string; rows: Row[] }

export type BudgetVerdict = "over" | "within" | "unknown";
export interface AlarmView {
  /** False alarms per hour, with its interval when there is one. */
  rate: Est | null;
  budget: number | null;
  verdict: BudgetVerdict;
  /** True when the whole interval is on one side of the budget. Null when there is no interval. */
  certain: boolean | null;
  /** Share of stuck spells the forecast flagged. */
  detection: Est | null;
}

/** Over or within the budget, by the point estimate, and whether the interval agrees. */
export function budgetVerdict(rate: Est | null, budget: number | null): { verdict: BudgetVerdict; certain: boolean | null } {
  if (!rate || budget === null || !isNum(budget)) return { verdict: "unknown", certain: null };
  const verdict: BudgetVerdict = rate.value > budget ? "over" : "within";
  if (!rate.ci) return { verdict, certain: null };
  const certain = verdict === "over" ? rate.ci[0] > budget : rate.ci[1] <= budget;
  return { verdict, certain };
}

export interface TtePair { n: number | null; predicted: number; observed: number }
export interface TteView {
  cIndex: Est | null;
  /** Concordance of the simple baseline, when the report gives it. */
  baselineC: Est | null;
  pairs: TtePair[];
  meanExpected: number | null;
  kmMean: number | null;
  /** Do the predicted minutes run above the observed ones? Null when it cannot be said. */
  runsHigh: boolean | null;
  /** True when this head belongs to a candidate that has not been accepted. */
  candidate: boolean;
}

export type Verdict = "accepted" | "null" | "harmful" | "not_run" | "no_primary";
const VERDICTS: Verdict[] = ["accepted", "null", "harmful", "not_run", "no_primary"];

export interface CardMeta {
  origin: "synthetic" | "real" | "mixed";
  n: number | null;
  nUnit: string;
  split: string | null;
  pool: string | null;
  level: number;
}

export interface Candidate {
  label: string;
  verdict: Verdict | null;
  meta: CardMeta;
  /** The candidate and v1 scored on the same pool, so they can share an axis. */
  logLoss: { candidate: Est | null; v1: Est | null };
  brier: { candidate: Est | null; v1: Est | null };
  falseAlarms: { candidate: Est | null; v1: Est | null };
  detection: { candidate: Est | null; v1: Est | null };
}

export interface Scorecard {
  source: "mlv2" | "hazard";
  /** Which model the charts call "our forecast". */
  version: "v1" | "v2";
  accepted: boolean | null;
  verdict: Verdict | null;
  /** One plain sentence when v1 stays the default. */
  defaultNote: string | null;
  label: string;
  meta: CardMeta;
  bins: Bin[];
  binsLabel: string | null;
  ece: Est | null;
  panels: MetricPanel[];
  alarms: AlarmView;
  perPerson: { id: string; label: string; falseAlarms: number | null; detection: number | null; bins: number | null }[];
  tte: TteView | null;
  /** The pool the v2 block was scored on (the time-to-progress head is scored there, not on v1's pool). */
  v2Meta: CardMeta | null;
  candidate: Candidate | null;
  caveats: string[];
  limits: string[];
  basis: string | null;
  intervalNote: string | null;
  /** Why Models v2 has no scorecard yet, when the report says. */
  v2Status: { status: string; reason: string | null } | null;
}

export type ScorecardRead =
  | { kind: "ready"; card: Scorecard }
  | { kind: "unavailable"; status: "missing" | "pending" | "not_run" | "failed"; what: string; reason: string };

/* -- Sections ----------------------------------------------------------------------------------- */

const STUBS = ["pending", "not_run", "failed"];
const stubOf = (s: unknown): { status: "pending" | "not_run" | "failed"; reason: string | null } | null =>
  isObj(s) && typeof s.status === "string" && STUBS.includes(s.status) ? { status: s.status as "pending" | "not_run" | "failed", reason: str(s.reason) } : null;

function metaOf(meta: unknown, extra?: Obj): CardMeta {
  const m = isObj(meta) ? meta : {};
  const o = m.origin === "real" || m.origin === "mixed" ? m.origin : "synthetic";
  return {
    origin: o, n: isNum(m.n) ? m.n : null, nUnit: str(m.n_unit) ?? "people", split: str(m.split), pool: str((extra ?? m).pool) ?? str(m.pool),
    level: isNum(m.interval_level) ? m.interval_level : 0.95,
  };
}

interface Block { logLoss: Est | null; brier: Est | null; ece: Est | null; fa: Est | null; detection: Est | null }

/** One model's numbers from a block like `{log_loss, brier, ece, false_alarms_per_hour, detection_rate}` (either `Est` or bare plus `ci_*`). */
function blockOf(b: unknown): Block {
  return {
    logLoss: estFrom(b, "log_loss"), brier: estFrom(b, "brier"), ece: estFrom(b, "ece"),
    fa: estFrom(b, "false_alarms_per_hour"), detection: estFrom(b, "detection_rate") ?? estFrom(b, "detection"),
  };
}

/** v1 `sections.hazard`: the model and its baselines, with false alarms and detection taken from the section's top level. */
function readHazard(h: Obj) {
  const model = blockOf(h.model);
  model.fa = estFrom(h, "false_alarms_per_hour");
  model.detection = estFrom(h, "detection_rate");
  const base = isObj(h.baselines) ? h.baselines : {};
  return {
    model, base: blockOf(base.base_rate), tsp: blockOf(base.time_since_progress),
    bins: readBins(h.calibration, false),
    budget: isNum(h.budget_false_alarms_per_hour) ? h.budget_false_alarms_per_hour : null,
    meta: metaOf(h.meta),
    basis: str(isObj(h.meta) ? h.meta.note : null),
    intervalNote: str(h.interval_note),
    caveats: arr(h.caveats).filter((c): c is string => typeof c === "string"),
    perPerson: isObj(h.per_person)
      ? Object.entries(h.per_person).filter(([, v]) => isObj(v)).map(([id, v]) => {
        const o = v as Obj;
        return { id, label: id.replace(/^p_/, "").replace(/_/g, " "), falseAlarms: isNum(o.false_alarms_per_hour) ? o.false_alarms_per_hour : null, detection: isNum(o.detection_rate) ? o.detection_rate : null, bins: isNum(o.n_bins) ? o.n_bins : null };
      })
      : [],
  };
}

function readTte(t: unknown, candidate: boolean): TteView | null {
  if (!isObj(t)) return null;
  const pairs: TtePair[] = arr(t.calibration).filter(isObj)
    .filter((p) => isNum(p.predicted_min) && isNum(p.observed_km_min))
    .map((p) => ({ n: isNum(p.n) ? p.n : null, predicted: p.predicted_min as number, observed: p.observed_km_min as number }));
  const cIndex = estOf(t.c_index);
  const meanExpected = isNum(t.mean_expected_min) ? t.mean_expected_min : null;
  const kmMean = isNum(t.km_restricted_mean_min) ? t.km_restricted_mean_min : null;
  if (!cIndex && !pairs.length && meanExpected === null) return null;
  const runsHigh = pairs.length ? pairs.every((p) => p.predicted > p.observed) : meanExpected !== null && kmMean !== null ? meanExpected > kmMean : null;
  return { cIndex, baselineC: estOf(t.baseline_c_index ?? t.c_index_baseline ?? t.c_index_tsp), pairs, meanExpected, kmMean, runsHigh, candidate };
}

const NOT_ACCEPTED: Record<Verdict, string> = {
  accepted: "",
  not_run: "has not been tested on held-out data yet",
  null: "did not beat v1 on held-out data",
  harmful: "did worse than v1 on held-out data",
  no_primary: "has no frozen candidate yet",
};

const VERDICT_WORD: Record<Verdict, string> = { accepted: "accepted", not_run: "not tested yet", null: "no gain", harmful: "worse than v1", no_primary: "no candidate" };
export const verdictWord = (v: Verdict | null): string => (v ? VERDICT_WORD[v] : "not accepted");

/**
 * Read the scorecard from the report. `example` is an `mlv2.scorecard`-shaped block to use when the report has none and the page is
 * showing example data (never in live mode).
 */
export function readScorecard(report: unknown, example?: unknown): ScorecardRead {
  const sections = isObj(report) && isObj(report.sections) ? report.sections : {};
  const hz = isObj(sections.hazard) ? sections.hazard : null;
  const hzStub = stubOf(hz);
  const hzOk = hz && !hzStub && isObj(hz.model) ? hz : null;

  const mv2 = isObj(sections.mlv2) ? sections.mlv2 : null;
  const mvStub = stubOf(mv2);
  const rawCard = mv2 && isObj(mv2.scorecard) ? mv2.scorecard : isObj(example) ? example : null;
  const sc = rawCard && (isObj(rawCard.model) || isObj(rawCard.baselines) || arr(rawCard.calibration).length) ? rawCard : null;

  if (!hzOk && !sc) {
    const stub = hzStub ?? mvStub;
    if (stub) return { kind: "unavailable", status: stub.status, what: hzStub ? "The stuck forecast" : "Models v2", reason: stub.reason ?? "No reason was given." };
    return { kind: "unavailable", status: "missing", what: "The stuck forecast", reason: "The report has no stuck-forecast section. Run make eval to write evals/report.json." };
  }

  const v1 = hzOk ? readHazard(hzOk) : null;
  const verdictRaw = sc ? sc.verdict : null;
  // ML2 words an acceptance by how it was earned ("accepted_by_both_tests"): any word starting "accepted" means accepted.
  const verdictNorm = typeof verdictRaw === "string" && verdictRaw.startsWith("accepted") ? "accepted" : verdictRaw;
  const verdict: Verdict | null = (VERDICTS as unknown[]).includes(verdictNorm) ? (verdictNorm as Verdict) : null;
  const accepted = sc ? sc.accepted === true && (verdict === null || verdict === "accepted") : null;

  const scMeta = sc ? metaOf(sc.meta, isObj(sc.meta) ? (sc.meta as Obj) : undefined) : null;
  const scBase = sc && isObj(sc.baselines) ? sc.baselines : {};
  const scModel = sc ? blockOf(sc.model) : null;
  const scV1 = sc ? blockOf(scBase.v1) : null;
  const scBaseRate = blockOf(scBase.base_rate);
  const scTsp = blockOf(scBase.time_since_progress);
  const scBins = sc ? readBins(sc.calibration, true) : [];
  const scBudget = sc && isNum(sc.budget_per_hour) ? sc.budget_per_hour : null;

  const useV2 = !!(sc && accepted && scModel);
  const ours: Block = useV2 ? (scModel as Block) : v1 ? v1.model : (scV1 as Block);
  const base: Block = v1 && !useV2 ? v1.base : scBaseRate;
  const tsp: Block = v1 && !useV2 ? v1.tsp : scTsp;
  const bins = useV2 && scBins.length ? scBins : v1 && v1.bins.length ? v1.bins : scBins;
  const binsLabel = useV2 && scBins.length ? str(sc?.calibration_source) : v1 && v1.bins.length ? "leave-one-person-out on the four generated people" : str(sc?.calibration_source);
  const meta = useV2 && scMeta ? scMeta : v1 ? v1.meta : (scMeta as CardMeta);
  const budget = useV2 ? scBudget ?? (v1 ? v1.budget : null) : v1 ? v1.budget ?? scBudget : scBudget;

  const nameOurs = useV2 ? str(sc?.primary_label) ?? "Our forecast (v2)" : "Our forecast (v1)";
  const rows = (pick: (b: Block) => Est | null, withV1: boolean): Row[] => {
    const r: Row[] = [{ id: "ours", label: nameOurs, est: pick(ours), ours: true }];
    if (useV2 && withV1 && scV1) r.push({ id: "v1", label: "Previous forecast (v1)", est: pick(scV1) });
    r.push({ id: "time_since_progress", label: "Time since progress only", est: pick(tsp) });
    r.push({ id: "base_rate", label: "Usual chance (base rate)", est: pick(base) });
    return r;
  };
  const panels: MetricPanel[] = [
    { key: "log_loss", title: "Log loss", rows: rows((b) => b.logLoss, true) },
    { key: "brier", title: "Brier score", rows: rows((b) => b.brier, true) },
  ].filter((p) => p.rows.some((r) => r.est)) as MetricPanel[];

  const rate = ours.fa ?? (sc ? estFrom(sc, "false_alarms_per_hour") : null);
  const detection = ours.detection ?? (sc ? estFrom(sc, "detection_rate") : null);
  const bv = budgetVerdict(rate, budget);

  const candidate: Candidate | null = sc && !useV2 && scModel && verdict !== "no_primary" && (scModel.logLoss || scModel.brier)
    ? {
      label: str(sc.primary_label) ?? "v2 candidate", verdict, meta: scMeta as CardMeta,
      logLoss: { candidate: scModel.logLoss, v1: scV1 ? scV1.logLoss : null }, brier: { candidate: scModel.brier, v1: scV1 ? scV1.brier : null },
      falseAlarms: { candidate: scModel.fa, v1: scV1 ? scV1.fa : null }, detection: { candidate: scModel.detection, v1: scV1 ? scV1.detection : null },
    }
    : null;

  const defaultNote = sc && !useV2
    ? `The v1 forecast stays the default. The v2 candidate ${NOT_ACCEPTED[verdict && verdict !== "accepted" ? verdict : "not_run"]}.`
    : null;
  const limits = arr(sections.limitations).filter(isObj).filter((l) => typeof l.id === "string" && /^ana-hazard/.test(l.id as string) && typeof l.text === "string").map((l) => l.text as string);

  const caveats = [...(v1 ? v1.caveats : []), ...(sc ? arr(sc.caveats).filter((c): c is string => typeof c === "string") : [])];
  const uniq = (xs: string[]) => xs.filter((x, i) => xs.indexOf(x) === i);

  const card: Scorecard = {
    source: useV2 || !v1 ? "mlv2" : "hazard", version: useV2 ? "v2" : "v1", accepted, verdict, defaultNote, label: nameOurs, meta,
    bins, binsLabel, ece: ours.ece, panels, alarms: { rate, budget, verdict: bv.verdict, certain: bv.certain, detection },
    perPerson: v1 ? v1.perPerson : [], tte: sc ? readTte(sc.tte, !useV2) : null, v2Meta: scMeta, candidate,
    caveats: uniq(caveats), limits: uniq(limits), basis: v1 ? v1.basis : null, intervalNote: v1 ? v1.intervalNote : null,
    v2Status: sc ? null : mvStub ? { status: mvStub.status, reason: mvStub.reason } : null,
  };
  return { kind: "ready", card };
}

/* -- Words for the sections --------------------------------------------------------------------- */

/** "0.436 (0.422 to 0.451)" or "0.436 (no interval yet)". */
export function fmtEst(e: Est | null, digits = 3): string {
  if (!e) return "not reported";
  const f = (x: number) => x.toFixed(digits);
  return e.ci ? `${f(e.value)} (${f(e.ci[0])} to ${f(e.ci[1])})` : `${f(e.value)} (no interval yet)`;
}
export function fmtPctEst(e: Est | null): string {
  if (!e) return "not reported";
  return e.ci ? `${pc(e.value)} (${pc(e.ci[0])} to ${pc(e.ci[1])})` : `${pc(e.value)} (no interval yet)`;
}

/** The one sentence under the baseline charts: is ours lower than each baseline, and what do the intervals say, measure by measure? */
export function baselineLine(panels: MetricPanel[]): string {
  if (!panels.length) return "No comparison with the baselines is in the report.";
  let any = false, allLower = true;
  const clear: string[] = [], overlap: string[] = [], missing: string[] = [];
  for (const p of panels) {
    const ours = p.rows.find((r) => r.ours)?.est ?? null;
    let state: "clear" | "overlap" | "missing" = "clear";
    for (const r of p.rows) {
      if (r.ours || (r.id !== "time_since_progress" && r.id !== "base_rate")) continue;
      const rel = relate(ours, r.est);
      if (rel.lower === null) continue;
      any = true;
      if (!rel.lower) allLower = false;
      if (rel.clear === null) { if (state === "clear") state = "missing"; }
      else if (!rel.clear) state = "overlap";
    }
    (state === "clear" ? clear : state === "overlap" ? overlap : missing).push(p.title.toLowerCase());
  }
  if (!any) return "The report does not give both numbers, so no comparison is drawn.";
  if (!allLower) return "Lower is better. On at least one measure ours is not lower than a baseline.";
  const list = (xs: string[]) => xs.join(" and ");
  const clauses: string[] = [];
  if (clear.length) clauses.push(`for ${list(clear)} the intervals do not overlap`);
  if (overlap.length) clauses.push(`for ${list(overlap)} the intervals overlap`);
  if (missing.length) clauses.push(`for ${list(missing)} the report gives no interval for a baseline`);
  return `Lower is better. Ours is lower than both baselines on every measure shown; ${clauses.join(", and ")}.`;
}

/** The baseline sentence for the page: one short line, with the detail about intervals kept for a Hint beside it. The full sentence stays in `baselineLine`. */
export function baselineShort(panels: Parameters<typeof baselineLine>[0]): { line: string; detail: string | null } {
  const full = baselineLine(panels);
  const m = /^Lower is better\. Ours is lower than both baselines on every measure shown; (.*)\.$/.exec(full);
  if (m) return { line: "Lower is better. Ours is lower on every measure shown.", detail: `About the intervals: ${m[1]}.` };
  return { line: full, detail: null };
}

/** Over or within the budget, in words that do not lean on colour. */
export function budgetWords(a: AlarmView): { title: string; detail: string } {
  if (a.verdict === "unknown" || !a.rate || a.budget === null) return { title: "No budget to compare with", detail: "The report gives no false-alarm budget." };
  const over = a.verdict === "over";
  const title = over ? "Over budget" : "Within budget";
  const where = a.certain === null
    ? "The report gives no interval, so this is the point estimate only."
    : a.certain
      ? over ? "The whole interval is above the budget." : "The whole interval is at or below the budget."
      : over ? "The interval reaches the budget, so it is over only by the point estimate." : "The interval goes above the budget, so it is within only by the point estimate.";
  return { title, detail: where };
}
