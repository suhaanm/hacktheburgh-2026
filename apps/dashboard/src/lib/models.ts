import type { Breaker, MeterRow, ModelProvider, ModelRole, ModelsStatus, ModelStep, PriceAssumption } from "../types";

/** Names that can hold a secret. A field called like this is dropped before anything is shown. */
const SECRET_KEY = /(^|_|-)(api_?key|key|secret|password|passwd|authorization|bearer|credential|access_token|auth_token|refresh_token|token)$/i;
/** Values that look like a key, whatever the field is called. */
const SECRET_VALUE = /^(sk-[\w-]{8,}|sk_[\w-]{8,}|AIza[\w-]{20,}|ya29\.[\w.-]{20,}|gh[pousr]_[\w]{20,}|xox[abprs]-[\w-]{10,}|Bearer\s+\S{12,}|eyJ[\w-]{10,}\.[\w-]{10,}\.[\w-]{5,}|[A-Fa-f0-9]{40,})$/;
/** A long run of mixed-case letters and digits is a token, not a model id (ids are lower case with dots and hyphens). */
function randomLooking(s: string): boolean {
  return /^[A-Za-z0-9+/_=-]{32,}$/.test(s) && /[a-z]/.test(s) && /[A-Z]/.test(s) && (s.match(/\d/g)?.length ?? 0) >= 3;
}
export const looksLikeKey = (s: string): boolean => SECRET_VALUE.test(s.trim()) || randomLooking(s.trim());

/** Remove anything that looks like a key, deeply. The page never shows one even if a service sends one by mistake. */
export function stripSecrets<T>(v: T): T {
  if (Array.isArray(v)) return v.map((x) => stripSecrets(x)) as unknown as T;
  if (v && typeof v === "object") {
    const out: Record<string, unknown> = {};
    for (const [k, x] of Object.entries(v as Record<string, unknown>)) {
      if (SECRET_KEY.test(k)) continue;
      out[k] = stripSecrets(x);
    }
    return out as T;
  }
  if (typeof v === "string" && looksLikeKey(v)) return "[removed]" as unknown as T;
  return v;
}

const obj = (x: unknown): Record<string, unknown> => (x && typeof x === "object" && !Array.isArray(x) ? (x as Record<string, unknown>) : {});
const str = (x: unknown): string | null => (typeof x === "string" && x ? x : null);
const num = (x: unknown): number | null => (typeof x === "number" && Number.isFinite(x) ? x : null);

function breakerOf(x: unknown): Breaker | null {
  const o = obj(x);
  if (!Object.keys(o).length) return null;
  return { state: str(o.state) ?? "unknown", recent_failures: num(o.recent_failures) ?? 0, retry_in_s: num(o.retry_in_s) ?? 0, opened_count: num(o.opened_count) ?? 0 };
}

/**
 * Read the status of the model layer. The agent service sends roles as a map and providers as a map (see
 * `understudy_agent.models.status.models_status`); a flat list of roles is accepted too. Nothing is assumed present.
 */
export function normaliseModelsStatus(raw: unknown): ModelsStatus {
  const r = obj(stripSecrets(raw));

  const roles: ModelRole[] = [];
  if (Array.isArray(r.roles)) {
    for (const x of r.roles) {
      const o = obj(x);
      const role = str(o.role) ?? "role";
      if (Array.isArray(o.steps)) {
        roles.push({ role, steps: (o.steps as unknown[]).map(stepOf), escalate: obj(o.escalate), call_timeout_s: num(o.call_timeout_s) ?? undefined, deadline_s: num(o.deadline_s) ?? undefined });
      } else {
        // The flat shape: one provider and model, one fallback.
        const steps: ModelStep[] = [{ provider: str(o.provider) ?? "unknown", tier: "", when: "primary", model: str(o.model_id) ?? str(o.model) }];
        const fb = str(o.fallback);
        if (fb) steps.push({ provider: fb, tier: "", when: "fallback", model: null });
        roles.push({ role, steps });
      }
    }
  } else {
    for (const [role, v] of Object.entries(obj(r.roles))) {
      const o = obj(v);
      roles.push({ role, steps: Array.isArray(o.steps) ? (o.steps as unknown[]).map(stepOf) : [], escalate: obj(o.escalate), call_timeout_s: num(o.call_timeout_s) ?? undefined, deadline_s: num(o.deadline_s) ?? undefined });
    }
  }

  const providers: ModelProvider[] = [];
  const pv = r.providers;
  const entries: [string, unknown][] = Array.isArray(pv) ? (pv as unknown[]).map((p) => [str(obj(p).name) ?? str(obj(p).provider) ?? "provider", p]) : Object.entries(obj(pv));
  for (const [name, v] of entries) {
    const o = obj(v);
    const models = Object.keys(obj(o.models)).length ? (Object.fromEntries(Object.entries(obj(o.models)).filter(([, m]) => typeof m === "string")) as Record<string, string>) : null;
    providers.push({
      name, configured: o.configured === true, enabled_by_flag: typeof o.enabled_by_flag === "boolean" ? o.enabled_by_flag : null,
      models, breaker: breakerOf(o.breaker), health: str(o.health) ?? "unknown",
    });
  }

  const boot = Object.entries(obj(r.boot)).map(([provider, v]) => {
    const o = obj(v);
    return { provider, t: str(o.t) ?? undefined, ok: typeof o.ok === "boolean" ? o.ok : undefined, mock: typeof o.mock === "boolean" ? o.mock : undefined, missing: Object.keys(obj(o.missing)) };
  });

  const latencies: Record<string, number[]> = {};
  for (const [k, v] of Object.entries(obj(r.last_latencies_ms))) if (Array.isArray(v)) latencies[k] = v.filter((n): n is number => typeof n === "number");

  const meter: MeterRow[] = Array.isArray(r.meter) ? (r.meter as unknown[]).map((x) => {
    const o = obj(x);
    return {
      role: str(o.role) ?? "", provider: str(o.provider) ?? "", model: str(o.model) ?? "", n: num(o.n) ?? 0, ok: num(o.ok) ?? 0, failed: num(o.failed) ?? 0,
      p50_ms: num(o.p50_ms), p95_ms: num(o.p95_ms), input_tokens: num(o.input_tokens) ?? 0, output_tokens: num(o.output_tokens) ?? 0, cost_usd_est: num(o.cost_usd_est),
    };
  }) : [];

  const prices: Record<string, PriceAssumption> = {};
  for (const [k, v] of Object.entries(obj(r.prices_assumed))) {
    const o = obj(v);
    prices[k] = { input_usd_per_million: num(o.input_usd_per_million) ?? 0, output_usd_per_million: num(o.output_usd_per_million) ?? 0, source: str(o.source) ?? "assumed" };
  }

  return {
    generated_at: str(r.generated_at) ?? "", mock: r.mock === true, roles, providers, boot, latencies, meter, prices_assumed: prices,
    config_error: str(r.config_error), bakeoff: r.bakeoff ?? null,
  };
}

function stepOf(x: unknown): ModelStep {
  const o = obj(x);
  return { provider: str(o.provider) ?? "unknown", tier: str(o.tier) ?? "", when: str(o.when) ?? "primary", model: str(o.model) };
}

/** Total estimated spend across the meter. `null` when no call has a price, so the page says "none yet" rather than $0. */
export function totalCost(meter: MeterRow[]): number | null {
  const priced = meter.filter((m) => typeof m.cost_usd_est === "number" && Number.isFinite(m.cost_usd_est));
  return priced.length ? priced.reduce((a, m) => a + (m.cost_usd_est ?? 0), 0) : null;
}

export function totalCalls(meter: MeterRow[]): { n: number; ok: number; failed: number } {
  return meter.reduce((a, m) => ({ n: a.n + m.n, ok: a.ok + m.ok, failed: a.failed + m.failed }), { n: 0, ok: 0, failed: 0 });
}

export function fmtUsd(v: number | null): string {
  if (v == null || !Number.isFinite(v)) return "none yet";
  if (v === 0) return "$0.00";
  if (v < 0.01) return "$" + v.toFixed(4);
  return v < 1 ? "$" + v.toFixed(3) : "$" + v.toFixed(2);
}

export function fmtMs(v: number | null): string {
  if (v == null || !Number.isFinite(v)) return "no calls yet";
  return v >= 1000 ? `${(v / 1000).toFixed(1)} s` : `${Math.round(v)} ms`;
}

export const WHEN_LABEL: Record<string, string> = { primary: "First", escalate: "If unsure", fallback: "If it fails" };

/** The health of a provider in plain words, and a tone for the pill. The breaker, when open, wins. */
export function healthReading(p: Pick<ModelProvider, "health" | "breaker" | "configured">): { label: string; tone: "good" | "warn" | "bad" | "muted" } {
  if (p.breaker?.state === "open") return { label: p.breaker.retry_in_s > 0 ? `Paused after failures, retrying in ${Math.ceil(p.breaker.retry_in_s)} s` : "Paused after failures", tone: "bad" };
  if (p.breaker?.state === "half_open" || p.breaker?.state === "half-open") return { label: "Trying again carefully", tone: "warn" };
  if (!p.configured) return { label: "Not set up", tone: "muted" };
  if (p.health === "ok") return { label: "Working", tone: "good" };
  if (p.health === "degraded") return { label: "Failing often", tone: "warn" };
  if (p.health === "down") return { label: "Down", tone: "bad" };
  return { label: "Not called yet", tone: "muted" };
}

export const ROLE_LABEL: Record<string, string> = {
  point: "Point at a target on screen",
  glance: "Read the screen state",
  verify: "Check an agent's work",
  planner: "Plan and run agents",
  fast: "Quick structured checks",
  computer_use: "Click and type (computer use)",
  live: "Talk with you (voice)",
};
export const roleLabel = (r: string): string => ROLE_LABEL[r] ?? r.replace(/_/g, " ");

/** Provider names are shown capitalised ("OpenAI", "Gemini"). */
export function providerName(p: string): string {
  const k = p.toLowerCase();
  return k === "openai" ? "OpenAI" : k === "gemini" ? "Gemini" : k === "local" ? "Local model" : p;
}

/**
 * Roles the router does not handle (planning, quick checks, computer use, voice) come straight from the resolved ids of the provider that is SET UP.
 * Gemini first when it is configured (that is what the engine's /health reports for these roles), then OpenAI; a provider with no key is never named
 * for a job it does not do. Nothing is shown when no provider is set up.
 */
export function directRoles(providers: ModelProvider[]): { role: string; provider: string; model: string }[] {
  const gm = providers.find((p) => p.name === "gemini" && p.configured && p.models);
  if (gm?.models) {
    const m = gm.models;
    const rows: [string, string | undefined][] = [["planner", m.accurate], ["fast", m.fast], ["computer_use", m.accurate], ["live", m.live]];
    return rows.filter((r): r is [string, string] => typeof r[1] === "string" && r[1] !== "").map(([role, model]) => ({ role, provider: "gemini", model }));
  }
  const oa = providers.find((p) => p.name === "openai" && p.configured && p.models);
  if (!oa?.models) return [];
  return (["planner", "fast", "computer_use"] as const)
    .filter((k) => typeof oa.models![k] === "string")
    .map((k) => ({ role: k, provider: "openai", model: oa.models![k] }));
}

/** The steps of a routed job that can actually run: a step whose provider is listed as not set up (no key) is left out, so the page never promises a fallback that is not there. */
export function usableSteps(role: ModelRole, providers: ModelProvider[]): ModelRole {
  const off = new Set(providers.filter((p) => !p.configured).map((p) => p.name));
  const steps = role.steps.filter((st) => !off.has(st.provider));
  return steps.length === 0 ? role : { ...role, steps };
}

/** Rows of an eval section as a table: only the scalar columns, in the order the first row gives them. Used for the bake-off and any section with no page of its own. */
export function scalarRows(rows: unknown, maxCols = 8): { cols: string[]; rows: Record<string, string>[] } {
  if (!Array.isArray(rows) || rows.length === 0) return { cols: [], rows: [] };
  const first = rows.find((r) => r && typeof r === "object") as Record<string, unknown> | undefined;
  if (!first) return { cols: [], rows: [] };
  const cols = Object.keys(first).filter((k) => ["string", "number", "boolean"].includes(typeof first[k])).slice(0, maxCols);
  const fmt = (v: unknown): string => (typeof v === "number" ? (Number.isInteger(v) ? String(v) : String(Math.round(v * 1000) / 1000)) : v == null ? "" : String(v));
  return { cols, rows: rows.filter((r) => r && typeof r === "object").map((r) => Object.fromEntries(cols.map((c) => [c, fmt((r as Record<string, unknown>)[c])]))) };
}

/** The most recent latencies of each provider and model, newest last, as "880, 910 and 1120 ms". */
export function latencyText(ms: number[]): string {
  if (ms.length === 0) return "none yet";
  return `${ms.map((m) => Math.round(m)).join(", ")} ms`;
}
