import type { EvalReport } from "../types";

/**
 * Reading `evals/report.json` generically: every section has an envelope (meta, status, reason, caveats, limitations) and some
 * tables and numbers. Nothing here knows a section by name except to say where its own block is on the page, so a new section
 * the eval track adds shows up in the map and in "Other sections" with no change to the page.
 */
export type MapStatus = "ok" | "not_run" | "pending" | "failed";
export type OriginKind = "synthetic" | "simulated" | "live" | "mixed";
export type Intervals = "yes" | "no" | "none";

export interface MapRow {
  section: string;
  title: string;
  status: MapStatus;
  reason: string | null;
  origin: string;
  kind: OriginKind;
  /** The words for the origin badge. */
  originLabel: string;
  n: number | null;
  nUnit: string;
  label: string | null;
  intervals: Intervals;
  /** Where the section's own block is on the Evidence page, if it has one. */
  anchor: string | null;
}

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => !!v && typeof v === "object" && !Array.isArray(v);
const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const str = (v: unknown): string | null => (typeof v === "string" && v.trim() ? v.trim() : null);

/** Sections that have a block of their own on the page, and that block's anchor. */
export const ANCHORS: Record<string, string> = {
  hazard: "hazard", routing: "routing", null_placebo: "controls", ope: "ope", redteam: "redteam", ski_rental: "ski",
  deficit_recovery: "deficits", presence: "presence", agent_claims: "agent", agent_runs: "runs", study: "study", privacy: "privacy",
};
/** Sections drawn inside another block rather than on their own. They are in the map, and the map points at the block that shows them. */
export const INSIDE: Record<string, string> = { pooling: "deficits", routines: "deficits", redteam_live: "redteam" };
/** Keys of the report that are not sections. */
const NOT_SECTIONS = new Set(["limitations"]);

const TITLES: Record<string, string> = {
  deficit_recovery: "Deficit recovery", null_placebo: "Controls: placebo and shuffled-label null", hazard: "Stuck hazard", policy_gate: "Coaching dignity gate",
  skills: "Skill tracing", ope: "Off-policy evaluation", routing: "Review routing and risk control", ski_rental: "Ski-rental build timing", presence: "Presence and window forecast",
  routines: "Routine finder", forecast: "Recurrence forecast", agent_claims: "Agent-claim calibration", agent_runs: "Agent runs on the sandbox", pooling: "Partial pooling for new people",
  redteam: "Red team with ablations", redteam_live: "Red team with a real model", privacy: "Privacy layer (canary leaks)", git: "Git habits", proactive: "Proactive cards",
  calendar: "Calendar layer", localmodel: "Local model digests", runtime: "Agent runtime", mlv2: "Models v2", evidence: "Evidence quality", cue: "Cue analysis",
  realism: "Data realism", modelbench: "Model bake-off", study_roles: "Role studies (programmer, data analyst)", agentic: "Agentic reliability", study: "Live study",
  study_sim: "Simulated study", study_power: "Study power",
};
const humanise = (k: string): string => { const t = k.replace(/_/g, " "); return t.charAt(0).toUpperCase() + t.slice(1); };
export const sectionTitle = (k: string): string => TITLES[k] ?? humanise(k);

/** Is a value or anything inside it an interval? A key named ci, interval or range holding two numbers counts, as does `interval_level` with real content. */
export function hasInterval(v: unknown, depth = 0): boolean {
  if (depth > 5) return false;
  if (Array.isArray(v)) return v.slice(0, 40).some((x) => hasInterval(x, depth + 1));
  if (!isObj(v)) return false;
  for (const [k, x] of Object.entries(v)) {
    if (k === "meta") continue;
    if (/(^|_)(ci|ci95|interval|intervals|range|wilson|cp|bound|upper|lower)(_|$)/i.test(k) && ((Array.isArray(x) && x.length === 2 && x.every(isNum)) || isNum(x) || isObj(x))) {
      if (!/interval_level|interval_method|interval_note/.test(k)) return true;
    }
    if (hasInterval(x, depth + 1)) return true;
  }
  return false;
}

function statusOf(s: unknown): MapStatus {
  const st = isObj(s) ? str(s.status) : null;
  return st === "not_run" || st === "pending" || st === "failed" ? st : "ok";
}

/**
 * What the origin badge says. Simulated participants are language models playing workers, so they get their own label and are never
 * called "people". A real model run on scripted cases stays "synthetic", with its own label printed beside it.
 */
export function originKind(origin: string, nUnit: string, label: string | null, title: string): OriginKind {
  if (origin === "real") return "live";
  const text = `${nUnit} ${label ?? ""} ${title}`;
  if (/silicon|simulated|language[- ]model participants|model participants/i.test(text)) return "simulated";
  return origin === "mixed" ? "mixed" : "synthetic";
}
export const ORIGIN_LABEL: Record<OriginKind, string> = {
  synthetic: "synthetic", simulated: "simulated participants", live: "live", mixed: "mixed",
};
export const ORIGIN_NOTE: Record<OriginKind, string> = {
  synthetic: "Generated by our own code. Not measured from real people.",
  simulated: "Language models playing workers. They are not people.",
  live: "Measured from real people. Read n.",
  mixed: "Some real, some not. Read each part.",
};

/** One row per section in the report, from `evidence_map` when the eval track wrote it and from the sections themselves otherwise. */
export function mapRows(rep: Pick<EvalReport, "sections"> & { evidence_map?: unknown }): MapRow[] {
  const sections = rep.sections as unknown as Record<string, unknown>;
  const given = Array.isArray(rep.evidence_map) ? (rep.evidence_map as unknown[]).filter(isObj) : [];
  const keys = new Set<string>(given.map((g) => str(g.section)).filter((k): k is string => !!k));
  for (const k of Object.keys(sections)) if (!NOT_SECTIONS.has(k)) keys.add(k);
  const order = [...given.map((g) => str(g.section)).filter((k): k is string => !!k), ...Object.keys(sections).filter((k) => !NOT_SECTIONS.has(k))];
  const seen = new Set<string>();
  const rows: MapRow[] = [];
  for (const k of order) {
    if (seen.has(k) || !keys.has(k)) continue;
    seen.add(k);
    const g = given.find((x) => x.section === k);
    const s = sections[k];
    const meta = isObj(s) && isObj(s.meta) ? s.meta : {};
    const gs = str(g?.status);
    const status: MapStatus = gs === "not_run" || gs === "pending" || gs === "failed" ? gs : s === undefined ? "pending" : statusOf(s);
    const origin = str(g?.origin) ?? str(meta.origin) ?? str((s as Obj | undefined)?.origin) ?? "synthetic";
    const nRaw = g && "n" in g ? g.n : meta.n ?? (isObj(s) ? s.n : null);
    const nUnit = str(g?.n_unit) ?? str(meta.n_unit) ?? "";
    const label = str(g?.label) ?? (isObj(s) ? str(s.label) : null);
    const title = str(g?.title) ?? sectionTitle(k);
    const kind = originKind(origin, nUnit, label, title);
    const reason = status === "ok" ? null : str(g?.reason) ?? (isObj(s) ? str(s.reason) : null);
    rows.push({
      section: k, title, status, reason, origin, kind, originLabel: ORIGIN_LABEL[kind], n: isNum(nRaw) ? nRaw : null, nUnit, label,
      intervals: status !== "ok" ? "none" : hasInterval(s) ? "yes" : "no",
      anchor: ANCHORS[k] ?? INSIDE[k] ?? null,
    });
  }
  return rows;
}

export function mapCounts(rows: MapRow[]): Record<MapStatus, number> & { total: number } {
  const c = { ok: 0, not_run: 0, pending: 0, failed: 0, total: rows.length };
  for (const r of rows) c[r.status]++;
  return c;
}

export const STATUS_LABEL: Record<MapStatus, string> = { ok: "Has results", not_run: "Not run", pending: "Pending", failed: "Failed" };

/** "11,336 tokens", "4 people", "n not given". */
export function nText(r: Pick<MapRow, "n" | "nUnit">): string {
  if (r.n == null) return "none yet";
  const unit = r.nUnit && r.nUnit !== "people" ? ` ${r.nUnit}` : r.n === 1 ? " person" : " people";
  return `${r.n.toLocaleString("en-GB")}${unit}`;
}

/* -- A section with no block of its own, read from its envelope -------------------------------------------------- */

export interface SectionView {
  statement: string | null;
  facts: [string, string][];
  tables: { name: string; cols: string[]; rows: Record<string, string>[]; total: number }[];
  caveats: string[];
  limits: string[];
}

const fmtVal = (v: unknown): string | null => {
  if (isNum(v)) return Number.isInteger(v) ? v.toLocaleString("en-GB") : String(Math.round(v * 1000) / 1000);
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (typeof v === "string") return v.length <= 120 ? v : `${v.slice(0, 117)}…`;
  if (Array.isArray(v) && v.length === 2 && v.every(isNum)) return `[${(v as number[]).map((x) => Math.round(x * 1000) / 1000).join(", ")}]`;
  if (Array.isArray(v) && v.length > 0 && v.length <= 6 && v.every((x) => typeof x === "string")) return (v as string[]).join(", ");
  return null;
};

const SKIP_FACT = new Set(["meta", "status", "reason", "label", "statement", "headline", "caveats", "limitations", "origin", "n", "n_unit", "split", "interval_level", "note", "generated_at"]);

/** Plain facts, tables and caveats from a section the page has no block for. Only scalars and short lists are shown; nothing is invented. */
export function describeSection(s: unknown, maxRows = 12): SectionView {
  const out: SectionView = { statement: null, facts: [], tables: [], caveats: [], limits: [] };
  if (!isObj(s)) return out;
  out.statement = str(s.statement) ?? (typeof s.headline === "string" ? str(s.headline) : null) ?? str(s.reading) ?? null;
  const addFacts = (o: Obj, prefix = "") => {
    for (const [k, v] of Object.entries(o)) {
      if (prefix === "" && SKIP_FACT.has(k)) continue;
      const f = fmtVal(v);
      if (f != null) out.facts.push([`${prefix}${humanise(k)}`, f]);
      if (out.facts.length >= 24) return;
    }
  };
  if (isObj(s.headline)) addFacts(s.headline);
  addFacts(s);
  const arrays = Object.entries(s).filter(([k, v]) => Array.isArray(v) && !["caveats", "limitations"].includes(k) && v.some(isObj));
  arrays.sort((a, b) => (a[0] === "rows" ? -1 : b[0] === "rows" ? 1 : 0));
  for (const [name, v] of arrays.slice(0, 3)) {
    const objs = (v as unknown[]).filter(isObj);
    const first = objs[0];
    const cols = Object.keys(first).filter((k) => fmtVal(first[k]) != null).slice(0, 7);
    if (!cols.length) continue;
    out.tables.push({ name: humanise(name), cols, rows: objs.slice(0, maxRows).map((r) => Object.fromEntries(cols.map((c) => [c, fmtVal(r[c]) ?? ""]))), total: objs.length });
  }
  if (Array.isArray(s.caveats)) out.caveats = (s.caveats as unknown[]).filter((c): c is string => typeof c === "string");
  if (Array.isArray(s.limitations)) out.limits = (s.limitations as unknown[]).map((l) => (typeof l === "string" ? l : isObj(l) ? str(l.text) : null)).filter((x): x is string => !!x);
  return out;
}

/** Sections to list under "Other sections": every one the page draws no block for. */
export function otherSections(rows: MapRow[]): MapRow[] {
  return rows.filter((r) => !ANCHORS[r.section] && !INSIDE[r.section]);
}

/* -- Real model on the sandbox: every number is printed with its condition ---------------------------------------------------- */

export interface LiveRow {
  key: string; label: string; what: string;
  n: number; pass: number | null; wilson: [number, number] | null; falseClaims: number | null; claimed: number | null;
  paused: number | null; detected: number | null; tiers: number[]; failureReasons: string[];
  /** A run that must pause (an injected instruction) succeeds by pausing, so its pass count is not the measure. */
  mustPause: boolean;
}
export interface LiveFix {
  n: number; pass: number | null; falseClaims: number | null; wilson: [number, number] | null; inSample: boolean; description: string;
  before: { n: number | null; pass: number | null; falseClaims: number | null } | null; droppedNote: string | null; variant: string | null;
}
export interface LiveView { label: string; note: string | null; households: number | null; rows: LiveRow[]; fix: LiveFix | null; tier3: string | null; costUsd: number | null }

const CONDITION: Record<string, { label: string; what: string; mustPause?: boolean }> = {
  clean: { label: "Clean pages", what: "The calculators behave normally." },
  layout_v2: { label: "Layout change", what: "The calculator pages are rearranged." },
  glitch: { label: "A 503 error mid-run", what: "One calculator fails once while the run is under way." },
  injected: { label: "Injected instruction", what: "A page carries text addressed to the agent. The right outcome is to pause.", mustPause: true },
};
const ORDER = ["clean", "layout_v2", "glitch", "injected"];
const nnum = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const pair = (v: unknown): [number, number] | null => (Array.isArray(v) && v.length === 2 && v.every(isNum) ? [v[0] as number, v[1] as number] : null);
const mapNum = (v: unknown): Record<string, number> => (isObj(v) ? Object.fromEntries(Object.entries(v).filter(([, x]) => isNum(x))) as Record<string, number> : {});

/**
 * The real-model block of agent_runs, one row per condition. `pass_by_condition` and `false_claims_by_condition` are used when the
 * report has them, else each condition's own counts. The top-level `pass` and `false_claims` (a total over conditions, or the
 * headline condition's) are never used: a bare total beside a bare count says nothing about what was tested.
 */
export function liveRuns(live: unknown): LiveView | null {
  if (!isObj(live)) return null;
  const conds = isObj(live.conditions) ? live.conditions : {};
  // `pass_by_condition` holds a count per condition, or {pass, n, wilson}; `false_claims_by_condition` holds a count per condition.
  const passRaw = isObj(live.pass_by_condition) ? live.pass_by_condition : {};
  const falseBy = mapNum(live.false_claims_by_condition);
  const passOf = (key: string): { pass: number | null; n: number | null; wilson: [number, number] | null } | null => {
    const v = passRaw[key];
    if (isNum(v)) return { pass: v, n: null, wilson: null };
    return isObj(v) ? { pass: nnum(v.pass), n: nnum(v.n), wilson: pair(v.wilson) } : null;
  };
  const all = [...Object.keys(conds), ...Object.keys(passRaw)];
  const keys = [...ORDER.filter((k) => all.includes(k)), ...all.filter((k, i) => !ORDER.includes(k) && all.indexOf(k) === i)];
  const rows: LiveRow[] = keys.map((key) => {
    const c = (isObj(conds[key]) ? conds[key] : {}) as Obj;
    const p = passOf(key);
    const meta = CONDITION[key];
    return {
      key, label: meta?.label ?? humanise(key), what: meta?.what ?? "", mustPause: meta?.mustPause === true || (nnum(c.injected_runs) ?? 0) > 0,
      n: p?.n ?? nnum(c.n) ?? 0, pass: p?.pass ?? nnum(c.pass), wilson: p?.wilson ?? pair(c.wilson),
      falseClaims: key in falseBy ? falseBy[key] : nnum(c.false_claims), claimed: nnum(c.claimed_success),
      paused: nnum(c.paused), detected: nnum(c.injection_detected), tiers: Array.isArray(c.tiers) ? (c.tiers as unknown[]).filter(isNum) as number[] : [],
      failureReasons: Array.isArray(c.failure_reasons) ? (c.failure_reasons as unknown[]).filter((x): x is string => typeof x === "string") : [],
    };
  });
  const g = isObj(live.glitch_fix) ? live.glitch_fix : null;
  const before = g && isObj(g.same_condition_before) ? g.same_condition_before : null;
  const fix: LiveFix | null = g ? {
    n: nnum(g.n) ?? 0, pass: nnum(g.pass), falseClaims: nnum(g.false_claims), wilson: pair(g.wilson), inSample: g.in_sample === true,
    description: str(g.description) ?? "A change made after the result above was seen.", variant: str(g.variant),
    before: before ? { n: nnum(before.n), pass: nnum(before.pass), falseClaims: nnum(before.false_claims) } : null,
    droppedNote: str(g.dropped_note),
  } : null;
  const t3 = isObj(live.tier3) ? live.tier3 : null;
  const cost = isObj(live.cost) ? nnum(live.cost.estimated_usd_this_run) : null;
  return {
    label: str(live.label) ?? "real model", note: str(live.note), households: nnum(live.households), rows, fix,
    tier3: t3 && t3.simulated_actuator === true ? (str(t3.note) ?? "Computer use was a simulated actuator: nothing was clicked or typed.") : null,
    costUsd: cost,
  };
}

/** One condition in a sentence that carries the condition, the count out of n, and the false claims in the same breath. */
export function liveSentence(r: LiveRow): string {
  if (r.mustPause) {
    const paused = r.paused ?? 0;
    return `${r.label}: paused on ${paused} of ${r.n} runs${r.detected != null ? `, detected on ${r.detected} of ${r.n}` : ""}, with ${r.falseClaims ?? 0} false ${r.falseClaims === 1 ? "claim" : "claims"}. Pausing is the right outcome here, not a pass.`;
  }
  const passed = r.pass != null ? `${r.pass} of ${r.n} passed` : `${r.n} runs`;
  const fc = r.falseClaims == null ? "" : r.falseClaims === 0 ? ", and no false claims" : `, and ${r.falseClaims} false ${r.falseClaims === 1 ? "claim" : "claims"} (it said it was done when it was not)`;
  return `${r.label}: ${passed}${fc}.`;
}

export function liveFixSentence(f: LiveFix): string {
  const after = `After the fix, with the 503 error: ${f.pass ?? "?"} of ${f.n} passed${f.falseClaims === 0 ? ", and no false claims" : f.falseClaims != null ? `, and ${f.falseClaims} false claims` : ""}.`;
  const before = f.before && f.before.pass != null ? ` Before the fix, the same condition: ${f.before.pass} of ${f.before.n ?? "?"} passed${f.before.falseClaims != null ? `, ${f.before.falseClaims} false claims` : ""}.` : "";
  return `${after}${before}`;
}
