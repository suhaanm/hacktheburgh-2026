// The computer-use rounds of the agent evaluation, side by side, read from `sections.agentic` of the eval report (the eval track writes them from its held-out runs).
// Pure: no React, no clock. Every sentence is built here from the numbers, so the page never says more than the data does. A round is one configuration (a provider,
// its models, a frozen build of the gate); rounds measure different things and are never pooled, so each is a row of its own. A round has a clean half (the agent does
// the work: completed with correct inputs, k of n, with a Wilson interval, against a bar fixed before the run) and an injected half (pages carry text aimed at an AI:
// the detector pauses the run, k of n).
export type Interval = [number, number];

export interface RoundHalf {
  k: number;
  n: number;
  wilson: Interval | null;
  /** The pre-registered bar, met or not. null when it was not tested (n too small, or the report does not say). */
  barMet: boolean | null;
  seed: number | null;
}

export interface Round {
  id: string;
  /** "Round 1" */
  label: string;
  /** "OpenAI" */
  provider: string;
  config: string;
  gateVersion: string | null;
  frozenGate: string | null;
  /** The gate that ran matches the build frozen for this round. null when the report does not say. */
  gateOk: boolean | null;
  clean: RoundHalf | null;
  injected: RoundHalf | null;
  /** Unexpected stops by the gate, reported apart from model failures (the newest clean run only). */
  unexpectedStops: number | null;
  falseClaims: number | null;
}

export interface Rounds {
  rounds: Round[];
  newest: Round | null;
  /** The bar's lower bound on the Wilson interval (0.8), when the report gives it. */
  barLower: number | null;
  headline: string;
}

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const str = (v: unknown): string | null => (typeof v === "string" && v.trim() ? v : null);
const pair = (v: unknown): Interval | null => (Array.isArray(v) && v.length === 2 && v.every(isNum) ? [v[0] as number, v[1] as number] : null);

const PROVIDERS: Record<string, string> = { openai: "OpenAI", gemini: "Gemini", anthropic: "Anthropic" };
export const providerName = (p: string | null): string => {
  if (!p) return "Unknown provider";
  return PROVIDERS[p.toLowerCase()] ?? `${p.charAt(0).toUpperCase()}${p.slice(1)}`;
};
/** "round2" is "Round 2"; anything else is shown as it came. */
export const roundLabel = (id: string): string => {
  const m = /^round[\s_-]*(\d+)$/i.exec(id);
  return m ? `Round ${m[1]}` : id.replace(/_/g, " ");
};
const roundNo = (id: string): number => {
  const m = /(\d+)/.exec(id);
  return m ? Number(m[1]) : Number.MAX_SAFE_INTEGER;
};
const providerOfConfig = (config: string | null, fallback: string | null): string | null => (fallback ? fallback : config ? (/^[a-z]+/i.exec(config)?.[0] ?? null) : null);

/** The share as a whole-number percentage pair: [70, 97]. */
const pctPair = (w: Interval): string => `${Math.round(w[0] * 100)} to ${Math.round(w[1] * 100)}%`;
/** "18 of 20 (70 to 97%)". */
export const halfFigure = (h: RoundHalf): string => `${h.k} of ${h.n}${h.wilson ? ` (${pctPair(h.wilson)})` : ""}`;

/** One word for the bar: "met", "not met", or why it is not tested. */
export function barWords(h: RoundHalf | null): string {
  if (!h) return "not run";
  if (h.barMet === true) return "met";
  if (h.barMet === false) return "not met";
  return h.n < 20 ? `not tested (n = ${h.n} is too few)` : "not tested";
}

function half(e: Record<string, unknown>, kind: "clean" | "injected"): RoundHalf | null {
  // The newest run keeps its figures in passed_code_check (clean) or paused_by_detector (injected); an earlier round carries k, n and wilson95 itself.
  const own = kind === "clean" ? e.passed_code_check : e.paused_by_detector;
  const src = isObj(own) ? own : e;
  const k = src.k, n = src.n;
  if (!isNum(k) || !isNum(n) || n <= 0) return null;
  const primary = isObj(e.primary) ? e.primary : null;
  const bar = kind === "clean" ? (typeof (primary?.bar_met ?? e.bar_met) === "boolean" ? ((primary?.bar_met ?? e.bar_met) as boolean) : null) : null;
  return { k, n, wilson: pair(src.wilson95), barMet: bar, seed: isNum(e.seed) ? e.seed : null };
}

/** The rounds in the `agentic` section of the report, oldest first; null when the section has none. */
export function agenticRounds(section: unknown): Rounds | null {
  if (!isObj(section)) return null;
  const heldout = isObj(section.heldout) ? section.heldout : null;
  const meta = Array.isArray(section.rounds) ? section.rounds.filter(isObj) : [];
  const byId = new Map<string, Round>();
  const get = (id: string): Round => {
    let r = byId.get(id);
    if (!r) {
      r = { id, label: roundLabel(id), provider: "", config: "", gateVersion: null, frozenGate: null, gateOk: null, clean: null, injected: null, unexpectedStops: null, falseClaims: null };
      byId.set(id, r);
    }
    return r;
  };
  for (const m of meta) {
    const id = str(m.id);
    if (!id) continue;
    const r = get(id);
    r.config = str(m.config) ?? r.config;
    r.provider = providerName(providerOfConfig(r.config, null));
    r.gateVersion = str(m.frozen_gate_version) ?? r.gateVersion;
    r.frozenGate = str(m.frozen_gate_version) ?? r.frozenGate;
    r.gateOk = typeof m.gate_version_ok === "boolean" ? m.gate_version_ok : r.gateOk;
  }
  const take = (kind: "clean" | "injected", entry: Record<string, unknown>, id: string) => {
    const r = get(id);
    const h = half(entry, kind);
    if (h) r[kind] = h;
    r.config = str(entry.config) ?? r.config;
    r.provider = providerName(providerOfConfig(r.config, str(entry.provider)));
    r.gateVersion = str(entry.gate_version) ?? r.gateVersion;
    r.frozenGate = str(entry.frozen_gate_version) ?? r.frozenGate;
    r.gateOk = typeof entry.gate_version_ok === "boolean" ? entry.gate_version_ok : r.gateOk;
    if (kind === "clean") {
      const stops = isObj(entry.gate_stops) && isNum(entry.gate_stops.unexpected) ? entry.gate_stops.unexpected : null;
      if (stops != null) r.unexpectedStops = stops;
      if (isNum(entry.false_claims)) r.falseClaims = entry.false_claims;
    }
  };
  let barLower: number | null = null;
  for (const kind of ["clean", "injected"] as const) {
    const newest = heldout && isObj(heldout[kind]) ? (heldout[kind] as Record<string, unknown>) : null;
    if (!newest) continue;
    const id = str(newest.round) ?? "round";
    take(kind, newest, id);
    if (kind === "clean" && isObj(newest.primary) && isNum(newest.primary.bar_lower_bound)) barLower = newest.primary.bar_lower_bound;
    for (const e of Array.isArray(newest.earlier_rounds) ? newest.earlier_rounds.filter(isObj) : []) take(kind, e, str(e.round) ?? "round");
  }
  const rounds = [...byId.values()].filter((r) => r.clean || r.injected).sort((a, b) => roundNo(a.id) - roundNo(b.id));
  if (!rounds.length) return null;
  const newest = rounds[rounds.length - 1];
  const earlier = rounds.length > 1 ? rounds[rounds.length - 2] : null;
  const parts: string[] = [];
  if (newest.clean) {
    const c = newest.clean;
    const bar = c.barMet === true ? "the pre-registered bar was met" : c.barMet === false ? "the pre-registered bar was not met" : "the pre-registered bar was not tested";
    parts.push(`The newest round (${newest.provider}): ${c.k} of ${c.n} households completed with correct inputs, and ${bar}.`);
  } else if (newest.injected) {
    parts.push(`The newest round (${newest.provider}) ran only the injected half: ${newest.injected.k} of ${newest.injected.n} pages paused.`);
  }
  if (earlier?.clean) {
    const e = earlier.clean;
    parts.push(`The earlier round (${earlier.provider}) did ${e.k} of ${e.n}${e.n < 20 ? ", too few to test the bar" : ""}; the two are not pooled.`);
  }
  return { rounds, newest, barLower, headline: parts.join(" ") };
}
