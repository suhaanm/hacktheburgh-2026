import { getState, noteSource, setState, whenExtReady } from "./store";
import type { ApprovalAuth } from "./auth/types";
import type {
  Analytic, AnalyticMeta, AuditLine, CoachState, EvalReport, Genome, Hazard, Health, KillState, Memory,
  AgentHealth, AgentKind, AgentRun, AgentRunDetail, AttentionDigest, AttentionPatch, AttentionPeek, AttentionSettings, Briefing, CalPerson, CalSuggestion, CalendarWeek, CoachDecision, CoachOutcome, ExtensionName, EvidencePacket, ExplainResult, GitHabits, GitPeople, LedgerEntry, LocalModelStatus, ModelsStatus, OffhoursReport, OnboardingAnswers, OnboardingQuestions, OnboardingResult, Pack, Presence, QueueItem, QuietHours,
  PrivacySummary, Prepared, Replay, Routine, RuleProposal, SpawnKind, Transitions, WorkGraph,
} from "./types";
import { classify, type Fallback } from "./lib/fallback";
import { isWrite, requestBody, requestHeaders, MISSING_HEADER, notReadyReason, type Actor } from "./lib/http";
import { FLAG_FOR } from "./lib/ext";
import { normaliseModelsStatus } from "./lib/models";
import genomeFx from "./fixtures/genome.json";
import transitionsFx from "./fixtures/transitions.json";
import presenceFx from "./fixtures/presence.json";
import routinesFx from "./fixtures/routines.json";
import queueFx from "./fixtures/queue.json";
import offhoursFx from "./fixtures/offhours.json";
import auditFx from "./fixtures/audit.json";
import workgraphFx from "./fixtures/workgraph.json";
import memoryFx from "./fixtures/memory.json";
import proposalsFx from "./fixtures/proposals.json";
import coachFx from "./fixtures/coach.json";
import packsFx from "./fixtures/packs.json";
import onboardingFx from "./fixtures/onboarding.json";
import hazardFx from "./fixtures/hazard.json";
import evalFx from "./fixtures/eval-report.json";
import healthFx from "./fixtures/health.json";
import weekFx from "./fixtures/calendar-week.json";
import suggestionsFx from "./fixtures/calendar-suggestions.json";
import briefingFx from "./fixtures/briefing.json";
import agentsFx from "./fixtures/agents-runs.json";
import ledgerFx from "./fixtures/privacy-ledger.json";
import privacySummaryFx from "./fixtures/privacy-summary.json";
import localModelFx from "./fixtures/localmodel-status.json";
import attentionSettingsFx from "./fixtures/attention-settings.json";
import attentionDigestFx from "./fixtures/attention-digest.json";
import attentionNextFx from "./fixtures/attention-next.json";
import evidencePacketFx from "./fixtures/evidence-packet.json";
import evidenceExplainFx from "./fixtures/evidence-explain.json";
import calPeopleFx from "./fixtures/calendar-people.json";
import gitHabitsFx from "./fixtures/git-habits.json";
import gitPeopleFx from "./fixtures/git-people.json";
import modelsFx from "./fixtures/models-status.json";
import agentKindsFx from "./fixtures/agents-kinds.json";
import { parseMemory, removeLineText, serializeMemory, toMemory } from "./lib/memory";
import { buildPreview } from "./lib/memoryPreview";
import { idleCapacity } from "./lib/heatmap";
import { dayKeys, normDays } from "./lib/days";

/**
 * The page calls its own origin under /engine and /agent; the Vite server forwards to ports 7700 and 7710 and adds the per-boot
 * token the services require for release actions (see vite.proxy.ts). VITE_ENGINE_URL and VITE_AGENT_URL can point at a service
 * directly, but then no token is added and the release buttons will say the engine is not ready.
 */
export const ENGINE_URL: string = (import.meta.env.VITE_ENGINE_URL as string | undefined) ?? "/engine";
export const AGENT_URL: string = (import.meta.env.VITE_AGENT_URL as string | undefined) ?? "/agent";
/** The engine as people name it, for messages. */
export const ENGINE_LABEL = "The engine (port 7700)";
/** The first calls to a cold engine are slow (a genome about 3 s, routines about 7 s, a hazard 6 to 12 s). Only a hung connection hits this. */
const TIMEOUT_MS = 40_000;

/** Writes carry who is acting. The engine refuses anything but the worker's own UI (403 write_refused). See lib/http.ts. */
export type { Actor };

export class ApiError extends Error {
  status: number;
  code: string;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export interface Loaded<T> {
  data: T;
  meta: AnalyticMeta | null;
  source: "live" | "demo";
  /** Set when `source` is "demo": why the screen shows example data. Null when the data is live. */
  why?: Fallback | null;
}

const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x)) as T;

/** A query string from the values that are set. */
function qs(p: Record<string, string | number | undefined | null>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(p)) if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
  const t = q.toString();
  return t ? `?${t}` : "";
}

/** A GET for a plain-text answer (the ledger export). */
async function sendText(base: string, path: string): Promise<{ ok: boolean; text: string }> {
  try {
    const res = await fetch(`${base}${path}`);
    return { ok: res.ok, text: res.ok ? await res.text() : "" };
  } catch {
    return { ok: false, text: "" };
  }
}

/** The summary the engine would give for the example ledger, so list and summary never disagree. */
function summariseDemoLedger(base: PrivacySummary, ledger: LedgerEntry[]): PrivacySummary {
  const sent = ledger.filter((e) => e.status !== "blocked");
  const by: Record<string, number> = {};
  for (const e of sent) by[e.purpose] = (by[e.purpose] ?? 0) + 1;
  const imgs = ledger.filter((e) => e.kind === "image");
  const blocked = imgs.filter((e) => e.status === "blocked");
  const okImgs = imgs.filter((e) => e.status !== "blocked");
  const count = (rows: LedgerEntry[], f: (e: LedgerEntry) => string | null | undefined) => {
    const o: Record<string, number> = {};
    for (const e of rows) { const k = f(e) ?? "unknown"; o[k] = (o[k] ?? 0) + 1; }
    return o;
  };
  return {
    ...base, calls: sent.length, by_purpose: by, last_call: sent[0]?.t ?? null,
    images: { sent: okImgs.length, blocked: blocked.length, blocked_by_reason: count(blocked, (e) => e.reason as string | null), sent_by_source: count(okImgs, (e) => e.source), bytes_sent: okImgs.reduce((a, e) => a + (e.image?.bytes ?? e.bytes ?? 0), 0), note: base.images?.note },
  };
}
const fx = <T,>(x: unknown) => x as T;

/** Accept both `{meta, data}` and a bare body, so a service that skips the envelope still works. */
function unwrap<T>(body: unknown): { data: T; meta: AnalyticMeta | null } {
  if (body && typeof body === "object" && !Array.isArray(body) && "data" in body && "meta" in body) {
    const b = body as Analytic<T>;
    return { data: b.data, meta: b.meta };
  }
  return { data: body as T, meta: null };
}

type Reached = { reached: true; status: number; body: unknown; tokenMissing?: boolean } | { reached: false; timedOut?: boolean };

/** After a network failure, skip that service for a few seconds: faster screens, no console spam. */
const downUntil = new Map<string, number>();
const BACKOFF_MS = 6000;
export function forgetBackoff(): void { downUntil.clear(); }

async function send(base: string, path: string, method: string, payload?: unknown, force = false, actor?: Actor, retried = false, timeoutMs = TIMEOUT_MS): Promise<Reached> {
  if (!force && (downUntil.get(base) ?? 0) > Date.now()) return { reached: false };
  const ctl = new AbortController();
  let timedOut = false;
  const timer = window.setTimeout(() => { timedOut = true; ctl.abort(); }, timeoutMs);
  try {
    // Every write carries JSON and the actor header, in this one place (lib/http.ts).
    const res = await fetch(`${base}${path}`, {
      method,
      signal: ctl.signal,
      headers: requestHeaders(method, actor),
      body: requestBody(method, payload),
    });
    let body: unknown = null;
    try { body = await res.json(); } catch { body = null; }
    // A service that restarted wrote a new token between our request and its answer: the dev server reads the file afresh on every
    // request, so asking once more picks the new one up. One retry only.
    if (!retried && res.status === 403 && isWrite(method) && (body as { error?: { code?: string } } | null)?.error?.code === "token_invalid") {
      return send(base, path, method, payload, force, actor, true, timeoutMs);
    }
    // The dev server says so when it found no per-boot token to add (see vite.proxy.ts).
    return { reached: true, status: res.status, body, tokenMissing: res.headers.get(MISSING_HEADER) === "missing" };
  } catch {
    // A refused connection means the service is down: skip it for a few seconds. A timeout means it is slow, not gone.
    if (!timedOut) downUntil.set(base, Date.now() + BACKOFF_MS);
    return { reached: false, timedOut };
  } finally {
    window.clearTimeout(timer);
  }
}

function toApiError(status: number, body: unknown, tokenMissing = false): ApiError {
  const e = (body as { error?: { code?: string; message?: string } } | null)?.error;
  const notReady = notReadyReason(status, e?.code, tokenMissing);
  if (notReady) return new ApiError(status, e?.code ?? "engine_not_ready", `${notReady}${e?.code ? ` (${e.code})` : ""}`);
  const plain: Record<number, string> = {
    403: "The engine refused this change because it did not come from your own app.",
    404: "The engine does not have that.",
    409: "That changed while you were looking. Reload and try again.",
    422: "The engine could not accept that. Check what you entered and try again.",
  };
  return new ApiError(status, e?.code ?? `http_${status}`, e?.message ?? plain[status] ?? `The service answered with status ${status}.`);
}

/** The service is down, or does not have this route yet: use demo data. */
const isMissing = (r: Reached) => !r.reached || r.status >= 500 || r.status === 404 || r.status === 405 || r.status === 501;

/** A write may fall back to the demo state only when nobody is there to take it: the service is down, or the route is absent or switched off.
 *  A 404 that carries an error body of its own ("There is no card x") is a real answer and is shown, not faked. A 5xx is an error to show. */
function writeMissing(r: Reached): boolean {
  if (!r.reached) return true;
  if (r.status === 405 || r.status === 501) return true;
  if (r.status === 404) return classify({ reached: true, status: 404, body: r.body }, { service: "x" }).kind !== "error";
  return false;
}

interface ReadOpts {
  who?: { service: string; flag?: string };
  /** Any answer but success becomes example data plus the reason, never an error screen. For optional extension screens. */
  soft?: boolean;
  /** The layer whose flag /health reports: when it is known to be off, do not ask. */
  layer?: ExtensionName;
}
const ENGINE_WHO = { service: "The engine" };
const AGENT_WHO = { service: "The agent service" };

/** The flag for a layer is known to be off: say so without making a request that would 404. */
function knownOff(layer: ExtensionName | undefined, who: { service: string }): Fallback | null {
  if (!layer) return null;
  const s = getState();
  if (!s.extReady || s.ext[layer] !== false) return null;
  // The agents flag comes from the agent service: believe it only when that service answered. (When the engine is unreachable every flag reads true.)
  if (layer === "agents" && s.agentUp !== true) return null;
  return { kind: "extension_off", status: 404, code: "extension_off", message: `This feature is switched off in ${who.service}. Start it with ${FLAG_FOR[layer]}=1 (or UNDERSTUDY_X=1 for every extension) to see your own data. Until then this screen shows example data.` };
}

async function read<T>(path: string, fallback: () => { data: T; meta?: AnalyticMeta | null }, base = ENGINE_URL, opts: ReadOpts = {}): Promise<Loaded<T>> {
  const who = opts.who ?? (base === AGENT_URL ? AGENT_WHO : ENGINE_WHO);
  const demoWith = (why: Fallback): Loaded<T> => {
    noteSource("demo");
    const f = fallback();
    return { data: clone(f.data), meta: f.meta ? clone(f.meta) : null, source: "demo", why };
  };
  if (opts.layer) {
    await whenExtReady();
    const off = knownOff(opts.layer, who);
    if (off) return demoWith(off);
  }
  const r = await send(base, path, "GET");
  const fail = { reached: r.reached, status: r.reached ? r.status : undefined, body: r.reached ? r.body : undefined };
  const flag = opts.layer ? FLAG_FOR[opts.layer] : opts.who?.flag;
  if (isMissing(r)) return demoWith(classify(fail, { ...who, flag }));
  if (r.reached && r.status >= 400) {
    if (opts.soft) return demoWith(classify(fail, { ...who, flag }));
    throw toApiError(r.status, r.body);
  }
  noteSource("live");
  const u = unwrap<T>(r.reached ? r.body : null);
  return { ...u, source: "live", why: null };
}

/** A write. When the service is down the demo state takes it, so the screen still works. */
async function write<T>(path: string, method: "POST" | "PUT", payload: unknown, fallback: () => T, actor: Actor = "worker", base = ENGINE_URL): Promise<{ data: T; source: "live" | "demo" }> {
  const r = await send(base, path, method, payload, false, actor);
  if (writeMissing(r)) {
    noteSource("demo");
    return { data: fallback(), source: "demo" };
  }
  if (r.reached && r.status >= 400) throw toApiError(r.status, r.body, r.tokenMissing);
  noteSource("live");
  return { data: unwrap<T>(r.reached ? r.body : null).data, source: "live" };
}

/* -- Demo state: what the fixtures become once the worker acts on them -------------------------- */
const demo = {
  routines: clone(fx<Analytic<Routine[]>>(routinesFx).data),
  queue: clone(fx<Analytic<QueueItem[]>>(queueFx).data),
  memory: clone(fx<Analytic<Memory>>(memoryFx).data),
  proposals: clone(fx<Analytic<RuleProposal[]>>(proposalsFx).data),
  quiet: clone(fx<Analytic<Presence>>(presenceFx).data.quiet_hours),
  workDeleted: new Set<string>(),
  killed: false,
  killedAt: null as string | null,
  briefing: clone(fx<Analytic<Briefing>>(briefingFx).data),
  runs: clone(fx<Analytic<AgentRun[]>>(agentsFx).data),
  ledger: clone(fx<Analytic<LedgerEntry[]>>(ledgerFx).data),
  attention: clone(fx<Analytic<AttentionSettings>>(attentionSettingsFx).data),
  spawned: 0,
};
const agentDetails = (agentsFx as unknown as { details: Record<string, AgentRunDetail> }).details;

/** Child roles a demo run is planned into, by kind. */
const DEMO_CHILDREN: Record<string, string[]> = {
  "programming.commit_analyst": ["commit reader", "habit counter"],
  "programming.test_gap": ["test finder"],
  "programming.refactor_suggest": ["code reader", "patch drafter"],
  "data.profile": ["profiler"],
  "data.chart": ["profiler", "chart builder"],
  "creative.weekly_summary": ["digest reader", "writer"],
};

function metaOf(fixture: unknown): AnalyticMeta | null {
  return (fixture as Analytic<unknown>).meta ?? null;
}
const dataOf = <T,>(fixture: unknown) => (fixture as Analytic<T>).data;

/* -- Reads ------------------------------------------------------------------------------------ */
export const api = {
  health: () => read<Health>("/health", () => ({ data: fx<Health>(healthFx) })),

  /** The agent service's own health. It carries the `agents` flag, which the engine does not know. Null when it does not answer. */
  agentHealth: async (): Promise<AgentHealth | null> => {
    const r = await send(AGENT_URL, "/health", "GET");
    if (!r.reached || r.status >= 400) return null;
    return unwrap<AgentHealth>(r.body).data ?? null;
  },

  genome: (task = "t_entitlement_check", person?: string, reference: "nearest_expert" | "consensus" = "nearest_expert") =>
    read<Genome>(`/genome/${encodeURIComponent(task)}?${new URLSearchParams({ ...(person ? { person } : {}), reference })}`, () => ({
      data: dataOf<Genome>(genomeFx),
      meta: metaOf(genomeFx),
    })),

  transitions: (task = "t_entitlement_check") =>
    read<Transitions>(`/graph/transitions?task=${encodeURIComponent(task)}`, () => ({ data: dataOf<Transitions>(transitionsFx), meta: metaOf(transitionsFx) })),

  replay: (person?: string, task?: string) =>
    read<Replay>(`/replay?${new URLSearchParams({ ...(person ? { person } : {}), ...(task ? { task } : {}), speed: "20", squeeze_idle_s: "30" })}`, () => ({
      data: { duration_s: 0, frames: [] },
    })),

  workGraph: (person?: string) =>
    read<WorkGraph>(`/graph/work${person ? `?person=${encodeURIComponent(person)}` : ""}`, () => {
      const d = dataOf<WorkGraph>(workgraphFx);
      const nodes = d.nodes.filter((n) => !demo.workDeleted.has(n.id));
      const ids = new Set(nodes.map((n) => n.id));
      return { data: { nodes, links: d.links.filter((l) => ids.has(l.a) && ids.has(l.b)) }, meta: metaOf(workgraphFx) };
    }),

  presence: async (person?: string): Promise<Loaded<Presence>> => {
    const r = await api.presenceRaw(person);
    // The engine sends day keys ("mon"); the screens use indexes. Accept both.
    r.data.quiet_hours = { ...r.data.quiet_hours, days: normDays(r.data.quiet_hours.days as unknown as (string | number)[]) };
    return r;
  },

  presenceRaw: (person?: string) =>
    read<Presence>(`/presence${person ? `?person=${encodeURIComponent(person)}` : ""}`, () => {
      const d = clone(dataOf<Presence>(presenceFx));
      d.quiet_hours = clone(demo.quiet);
      d.idle_capacity_h = idleCapacity(d.bins, d.quiet_hours);
      return { data: d, meta: metaOf(presenceFx) };
    }),

  routines: () => read<Routine[]>("/routines", () => ({ data: demo.routines, meta: metaOf(routinesFx) })),

  queue: (status: "pending" | "all" = "all") =>
    read<QueueItem[]>(`/queue?status=${status}`, () => ({
      data: status === "pending" ? demo.queue.filter((q) => q.status === "pending") : demo.queue,
      meta: metaOf(queueFx),
    })),

  offhoursReport: (since?: string) =>
    read<OffhoursReport>(`/offhours/report${since ? `?since=${encodeURIComponent(since)}` : ""}`, () => ({ data: dataOf<OffhoursReport>(offhoursFx), meta: metaOf(offhoursFx) })),

  audit: (limit = 50) => read<AuditLine[]>(`/audit?limit=${limit}`, () => ({ data: dataOf<AuditLine[]>(auditFx), meta: metaOf(auditFx) })),

  memory: () => read<Memory>("/memory", () => ({ data: demo.memory, meta: metaOf(memoryFx) })),

  proposals: () => read<RuleProposal[]>("/memory/proposals", () => ({ data: demo.proposals, meta: metaOf(proposalsFx) })),

  coach: (person?: string) =>
    read<CoachState>(`/coach/state${person ? `?person=${encodeURIComponent(person)}` : ""}`, () => ({ data: dataOf<CoachState>(coachFx), meta: metaOf(coachFx) })),

  /**
   * The live coach brain. Polling without `dry` advances its dignity gate, so call it at a steady pace (about every 3 s);
   * use `dry` for a passive look. Without the engine, a decision is built from the demo coach state.
   */
  coachNext: (person: string, dry: boolean) =>
    read<CoachDecision>(`/coach/next?person=${encodeURIComponent(person)}${dry ? "&dry=1" : ""}`, () => {
      const c = dataOf<CoachState>(coachFx);
      const d: CoachDecision = {
        action: "nudge", message: c.message, why: c.why, target: null, missed: [], confidence: 0.8, level: c.level, chip: c.chip,
        decision_id: "d_demo", task_id: c.task.id, step: c.task.step, trigger: "demo data", reason_codes: [],
        gate: { consecutive: 2, reason: "demo data" }, p_stuck: null, p_source: null, candidate: null, mastery: c.mastery,
      };
      return { data: d, meta: metaOf(coachFx) };
    }),

  /** Tell the coach what the worker did with a decision. Sent as the worker. */
  coachFeedback: (decision_id: string, outcome: CoachOutcome) =>
    write<{ ok?: boolean }>("/coach/feedback", "POST", { decision_id, outcome }, () => ({ ok: true })),

  packs: () => read<Pack[]>("/packs", () => ({ data: fx<Pack[]>(packsFx) })),

  onboardingQuestions: (role: string) =>
    read<OnboardingQuestions>(`/onboarding/questions?role=${encodeURIComponent(role)}`, () => ({
      data: fx<Record<string, OnboardingQuestions>>(onboardingFx)[role] ?? fx<Record<string, OnboardingQuestions>>(onboardingFx)["benefits-processor"],
    })),

  hazard: (person = "p_novice_03") => read<Hazard>(`/hazard/${encodeURIComponent(person)}`, () => ({ data: dataOf<Hazard>(hazardFx), meta: metaOf(hazardFx) })),

  evalReport: () =>
    read<EvalReport>("/eval/report", () => ({ data: fx<EvalReport>(evalFx), meta: null })),

  /* -- Extensions (REQ-2): each is flag-gated; without the engine the fixtures answer ----------------------------- */
  calendarWeek: (person?: string, week?: string) =>
    read<CalendarWeek>(`/calendar/week${qs({ person, week })}`, () => ({ data: dataOf<CalendarWeek>(weekFx), meta: metaOf(weekFx) }), ENGINE_URL, { layer: "calendar", soft: true }),

  /** Who has a calendar (additive route): drives the person and week pickers. */
  calendarPeople: () =>
    read<CalPerson[]>("/calendar/people", () => ({ data: dataOf<CalPerson[]>(calPeopleFx), meta: metaOf(calPeopleFx) }), ENGINE_URL, { layer: "calendar", soft: true }),

  calendarSuggestions: (person?: string, week?: string) =>
    read<CalSuggestion[]>(`/calendar/suggestions${qs({ person, week })}`, () => ({ data: dataOf<CalSuggestion[]>(suggestionsFx), meta: metaOf(suggestionsFx) }), ENGINE_URL, { layer: "calendar", soft: true }),

  briefing: (person?: string) =>
    read<Briefing>(`/briefing${qs({ person })}`, () => ({ data: demo.briefing, meta: metaOf(briefingFx) }), ENGINE_URL, { layer: "proactive", soft: true }),

  /** Edit the prepared block. The body is the prepared content itself: { text?, steps? }. */
  briefingEdit: (id: string, prepared: Prepared) =>
    write<unknown>(`/briefing/${encodeURIComponent(id)}/prepared`, "PUT", prepared, () => {
      const c = demo.briefing.cards.find((x) => x.id === id);
      if (!c) throw new ApiError(404, "no_such_card", "That card is gone.");
      c.prepared = clone(prepared);
      return { ok: true };
    }),

  /** Press to fire. Only the worker's press does this. Returns what it created: an approval item, a background run, or both. */
  briefingFire: async (id: string): Promise<{ queue_id?: string; run_id?: string }> => {
    const r = await write<{ queue_id?: string; run_id?: string }>(`/briefing/${encodeURIComponent(id)}/fire`, "POST", undefined, () => {
      const c = demo.briefing.cards.find((x) => x.id === id);
      if (!c) throw new ApiError(404, "no_such_card", "That card is gone.");
      if (c.status !== "ready") throw new ApiError(409, "not_ready", "That card is no longer ready.");
      const out = c.kind === "automate" || c.kind === "agent_result" ? { run_id: `r_demo_${c.id}` } : { queue_id: `q_demo_${c.id}` };
      c.status = "fired";
      c.fired = out;
      return out;
    }, "worker_approval");
    return r.data ?? {};
  },

  /** "Not now" and "Never for this" both dismiss; `mode` is additive and tells the engine which. */
  briefingDismiss: (id: string, mode: "not_now" | "never") =>
    write<unknown>(`/briefing/${encodeURIComponent(id)}/dismiss`, "POST", { mode }, () => {
      const c = demo.briefing.cards.find((x) => x.id === id);
      if (!c) throw new ApiError(404, "no_such_card", "That card is gone.");
      c.status = "dismissed";
      return { ok: true };
    }),

  agentsRuns: (person?: string) =>
    read<AgentRun[]>(`/agents/runs${qs({ person })}`, () => ({ data: demo.runs, meta: metaOf(agentsFx) }), AGENT_URL, { layer: "agents", soft: true }),

  agentsRunDetail: (id: string) =>
    read<AgentRunDetail>(`/agents/runs/${encodeURIComponent(id)}`, () => ({ data: agentDetails[id] ?? { artifacts: [], result: null } }), AGENT_URL, { layer: "agents", soft: true }),

  /** The jobs this service can run, with plain titles. Falls back to the six the contract names. */
  agentsKinds: () =>
    read<AgentKind[]>("/agents/kinds", () => ({ data: fx<AgentKind[]>(agentKindsFx) }), AGENT_URL, { layer: "agents", soft: true }),

  agentsSpawn: async (kind: SpawnKind, mode: "foreground" | "nightly", params: Record<string, unknown> = {}): Promise<{ run_id: string }> => {
    const r = await write<{ run_id: string }>("/agents/spawn", "POST", { kind, params, mode }, () => {
      const run_id = `r_demo_${++demo.spawned}`;
      const b = (steps: number, seconds: number, tokens: number) => ({ steps, seconds, tokens });
      demo.runs.unshift({
        run_id, kind, mode, state: mode === "nightly" ? "queued" : "running", started: new Date().toISOString(),
        parent: { id: `p_${run_id}`, role: "planner", state: mode === "nightly" ? "queued" : "running", budget: b(20, 300, 12000), spent: b(0, 0, 0) },
        children: (DEMO_CHILDREN[kind] ?? ["worker"]).map((role, i) => ({ id: `c_${run_id}_${i}`, role, state: "queued", budget: b(12, 120, 5000), spent: b(0, 0, 0) })),
      });
      return { run_id };
    }, "worker", AGENT_URL);
    return r.data;
  },

  agentsStop: (id: string) =>
    write<unknown>(`/agents/runs/${encodeURIComponent(id)}/stop`, "POST", undefined, () => {
      const run = demo.runs.find((x) => x.run_id === id);
      if (!run) throw new ApiError(404, "no_such_run", "That run is gone.");
      const stop = (n: { state: string }) => { if (["running", "queued", "paused", "starting"].includes(n.state)) n.state = "stopped"; };
      stop(run); stop(run.parent); run.children.forEach(stop);
      return { stopped: true };
    }, "worker", AGENT_URL),

  /** End one child at once (a parent revoke cascades to its children). Sent as the worker. */
  agentsRevoke: (runId: string, childId: string) =>
    write<unknown>(`/agents/runs/${encodeURIComponent(runId)}/children/${encodeURIComponent(childId)}/revoke`, "POST", undefined, () => {
      const run = demo.runs.find((x) => x.run_id === runId);
      const child = run?.children.find((c) => c.id === childId);
      if (!run || !child) throw new ApiError(404, "no_such_child", "That child is gone.");
      child.state = "revoked";
      if (child.lease) { child.lease.revoked = true; child.lease.remaining_s = 0; }
      return { revoked: true };
    }, "worker", AGENT_URL),

  privacyLedger: (limit = 200) =>
    read<LedgerEntry[]>(`/privacy/ledger?limit=${limit}`, () => ({ data: demo.ledger, meta: metaOf(ledgerFx) }), ENGINE_URL, { layer: "privacy", soft: true }),

  privacySummary: () =>
    read<PrivacySummary>("/privacy/summary", () => {
      const base = dataOf<PrivacySummary>(privacySummaryFx);
      return { data: summariseDemoLedger(base, demo.ledger), meta: metaOf(privacySummaryFx) };
    }, ENGINE_URL, { layer: "privacy", soft: true }),

  /** What the worker saves: the engine's own export (JSON lines, oldest first) when it is there, else the list on screen. */
  privacyExport: async (): Promise<{ text: string; source: "live" | "demo" }> => {
    const r = await sendText(ENGINE_URL, "/privacy/ledger/export");
    if (r.ok) return { text: r.text, source: "live" };
    return { text: demo.ledger.map((e) => JSON.stringify(e)).join("\n") + (demo.ledger.length ? "\n" : ""), source: "demo" };
  },

  privacyClear: () =>
    write<{ cleared?: number; blocked_cleared?: number; at?: string }>("/privacy/ledger/clear", "POST", undefined, () => { const n = demo.ledger.length; demo.ledger = []; return { cleared: n, blocked_cleared: 0, at: new Date().toISOString() }; }),

  localModel: () => read<LocalModelStatus>("/localmodel/status", () => ({ data: fx<LocalModelStatus>(localModelFx) }), ENGINE_URL, { layer: "localmodel", soft: true }),

  gitPeople: () => read<GitPeople>("/git/people", () => ({ data: fx<Analytic<GitPeople>>(gitPeopleFx).data ?? fx<GitPeople>(gitPeopleFx), meta: null }), ENGINE_URL, { layer: "git", soft: true }),

  gitHabits: (person?: string, repo?: string) =>
    read<GitHabits>(`/git/habits${qs({ person, repo })}`, () => ({ data: dataOf<GitHabits>(gitHabitsFx), meta: metaOf(gitHabitsFx) }), ENGINE_URL, { layer: "git", soft: true }),

  /** Notices: how loudly each kind of notice speaks, the day's budget and what was learned. Metadata only. */
  attentionSettings: (person?: string) =>
    read<AttentionSettings>(`/attention/settings${qs({ person })}`, () => ({ data: demo.attention, meta: metaOf(attentionSettingsFx) }), ENGINE_URL, { layer: "attention", soft: true }),

  /** The "Today" strip, from fixed lines and counts. `kind` is now, morning or return. */
  attentionDigest: (person?: string, kind: "now" | "morning" | "return" = "now") =>
    read<AttentionDigest>(`/attention/digest${qs({ person, kind })}`, () => ({ data: dataOf<AttentionDigest>(attentionDigestFx), meta: metaOf(attentionDigestFx) }), ENGINE_URL, { layer: "attention", soft: true }),

  /** Passive counts for the banner. A peek delivers nothing; the desktop owns what is drawn on screen. */
  attentionPeek: (person?: string) =>
    read<AttentionPeek>(`/attention/next${qs({ person, peek: 1 })}`, () => ({ data: dataOf<AttentionPeek>(attentionNextFx), meta: metaOf(attentionNextFx) }), ENGINE_URL, { layer: "attention", soft: true }),

  /** Change a setting. Safety kinds are fixed: the engine answers 422 safety_fixed and the screen shows its words. Sent as the worker. */
  attentionSet: (patch: AttentionPatch, person?: string) =>
    write<AttentionSettings>(`/attention/settings${qs({ person })}`, "POST", patch, () => {
      const s = demo.attention;
      for (const [type, mode] of Object.entries(patch.modes ?? {})) {
        const row = s.types.find((t) => t.type === type);
        if (!row) throw new ApiError(422, "unknown_type", `There is no kind of notice called ${type}.`);
        if (row.fixed) throw new ApiError(422, "safety_fixed", "Safety stops cannot be changed. They are always shown once and stay visible until resolved.");
        row.mode = mode;
        if (mode === "normal") delete s.modes[type]; else s.modes[type] = mode;
      }
      if (typeof patch.budget_per_day === "number") s.budget_per_day = patch.budget_per_day;
      if (typeof patch.level_glance === "boolean") s.level_glance = patch.level_glance;
      if (patch.reset_learned === true) s.learned = {};
      else if (Array.isArray(patch.reset_learned)) for (const t of patch.reset_learned) delete s.learned[t];
      return clone(s);
    }),

  /** The numbers an explanation is built from. Each cited path in an explanation is looked up here. */
  evidencePacket: (person?: string, caseId?: string) =>
    read<EvidencePacket>(`/evidence/packet${qs({ person, case: caseId })}`, () => ({ data: dataOf<EvidencePacket>(evidencePacketFx), meta: metaOf(evidencePacketFx) }), ENGINE_URL, { layer: "evidence", soft: true }),

  /**
   * "Where did my time go?" The words, the source that wrote them and the check's verdict. A write because it may call a model, so it
   * carries the worker actor. The first call to a local model can take about two minutes, hence the long wait. The question is sent
   * to the engine and nowhere else: it is not kept, logged or put in a URL. `hint` only picks which example answer to show when the
   * engine is not there; it is never sent.
   */
  evidenceExplain: async (body: { person?: string; case?: string; question?: string; include_packet?: boolean }, hint = "where_time_went"): Promise<Loaded<ExplainResult>> => {
    const example = (why: Fallback): Loaded<ExplainResult> => {
      noteSource("demo");
      const fx = evidenceExplainFx as unknown as Record<string, Analytic<ExplainResult>>;
      const pick = fx[hint] ?? fx.default;
      return { data: clone(pick.data), meta: clone(pick.meta), source: "demo", why };
    };
    await whenExtReady();
    const off = knownOff("evidence", ENGINE_WHO);
    if (off) return example(off);
    const r = await send(ENGINE_URL, "/evidence/explain", "POST", body, false, "worker", false, 180_000);
    const fail = { reached: r.reached, status: r.reached ? r.status : undefined, body: r.reached ? r.body : undefined };
    if (writeMissing(r)) return example(classify(fail, { ...ENGINE_WHO, flag: FLAG_FOR.evidence }));
    if (r.reached && r.status >= 400) throw toApiError(r.status, r.body, r.tokenMissing);
    noteSource("live");
    const u = unwrap<ExplainResult>(r.reached ? r.body : null);
    return { ...u, source: "live", why: null };
  },

  /** Model roles, provider health, breakers, latencies and the cost meter. Read from the agent service; the route may not be wired yet. */
  modelsStatus: async (): Promise<Loaded<ModelsStatus>> => {
    const r = await read<unknown>("/models/status", () => ({ data: modelsFx as unknown }), AGENT_URL, { soft: true, who: { service: "The agent service" } });
    return { ...r, data: normaliseModelsStatus(r.data) };
  },

  /** Optional route (additive): the kill flag as the engine sees it. Absent routes fall back to local state. */
  killState: () => read<KillState>("/kill", () => ({ data: { killed: demo.killed, at: demo.killedAt } })),

  /* -- Writes ---------------------------------------------------------------------------------- */
  async kill(): Promise<{ killed: boolean; at: string | null }> {
    const at = new Date().toISOString();
    const r = await send(ENGINE_URL, "/kill", "POST", undefined, true);
    if (r.reached && r.status < 400) {
      noteSource("live");
      const b = unwrap<KillState>(r.body).data;
      return { killed: b?.killed ?? true, at: b?.at ?? at };
    }
    // The engine could not be reached or refused: go to the agent directly. Stopping must never wait on the engine.
    const a = await send(AGENT_URL, "/kill", "POST", undefined, true);
    if (a.reached && a.status < 400) return { killed: true, at };
    if (!r.reached && !a.reached) {
      noteSource("demo");
      demo.killed = true;
      demo.killedAt = at;
      return { killed: true, at };
    }
    throw new ApiError(r.reached ? r.status : 0, "kill_failed", "The stop request was not accepted. Close the desktop app, or run: touch data/KILL");
  },

  async clearKill(): Promise<{ killed: boolean; at: string | null }> {
    const r = await write<KillState>("/kill/clear", "POST", undefined, () => {
      demo.killed = false;
      demo.killedAt = null;
      return { killed: false, at: null };
    });
    return { killed: r.data?.killed ?? false, at: r.data?.at ?? null };
  },

  /** `skill_override` re-sends a consent the skill gate refused (422 skill_gate); the engine records it in the memory file. */
  setConsent: (id: string, body: { mode: string; irreversible_unattended?: string[]; typed_confirm?: string; skill_override?: boolean }) =>
    write<Routine>(`/routines/${encodeURIComponent(id)}/consent`, "POST", { irreversible_unattended: [], typed_confirm: "", ...body }, () => {
      const r = demo.routines.find((x) => x.id === id);
      if (!r) throw new ApiError(404, "no_such_routine", `There is no routine called ${id}.`);
      const irreversible = body.irreversible_unattended ?? [];
      if (["shadow", "approval", "unattended"].includes(body.mode) && !r.skill_gate.eligible && !body.skill_override) {
        throw new ApiError(422, "skill_gate", r.skill_gate.reason);
      }
      if (body.mode === "unattended" && irreversible.length && r.driver === "model" && body.typed_confirm !== r.id) {
        throw new ApiError(422, "typed_confirmation_required", `Type ${r.id} exactly to allow irreversible steps while you are away.`);
      }
      const map: Record<string, Routine["status"]> = { not_now: "declined", never: "never", shadow: "shadow", approval: "approval", unattended: "unattended" };
      r.status = map[body.mode] ?? r.status;
      r.consent = { mode: body.mode, irreversible_unattended: irreversible, typed_confirm: body.typed_confirm ? true : false };
      if (body.mode === "shadow" && r.rung === "A0") r.rung = "A1";
      if (body.mode === "not_now" || body.mode === "never") r.rung = "A0";
      return clone(r);
    }),

  /** Who the engine says the worker is, once onboarding has run. 404 before that. */
  identity: async (): Promise<{ person: string; role: string } | null> => {
    const r = await send(ENGINE_URL, "/identity", "GET");
    if (!r.reached || r.status >= 400) return null;
    noteSource("live");
    const b = unwrap<{ person: string; role: string }>(r.body).data;
    return b?.person ? b : null;
  },

  /** `auth` is additive and only sent with an approval: { method, sub_hash? }. Never an email, a name or a token. */
  setQueue: (id: string, action: "approve" | "reject", auth?: ApprovalAuth) =>
    write<QueueItem>(`/queue/${encodeURIComponent(id)}/${action}`, "POST", action === "approve" && auth ? { auth } : undefined, () => {
      const q = demo.queue.find((x) => x.id === id);
      if (!q) throw new ApiError(404, "no_such_item", `There is no queue item ${id}.`);
      q.status = action === "approve" ? "approved" : "rejected";
      q.decided_at = new Date().toISOString();
      q.decided_by = "human";
      return clone(q);
    }, action === "approve" ? "worker_approval" : "worker"),

  putQuietHours: async (q: QuietHours): Promise<QuietHours> => {
    const r = await write<QuietHours>("/presence/quiet_hours", "PUT", { ...q, days: dayKeys(q.days) }, () => {
      demo.quiet = clone(q);
      return clone(q);
    });
    return { ...r.data, days: normDays(r.data.days as unknown as (string | number)[]) };
  },

  decide: (d_min: number, gain: number, loss: number) =>
    write<{ go: boolean; survival: number; threshold: number; reason: string; locked: boolean }>("/offhours/decide", "POST", { d_min, gain, loss }, () => {
      const f = dataOf<Presence>(presenceFx).forecast;
      const s = f.reduce((best, p) => (Math.abs(p.d_min - d_min) < Math.abs(best.d_min - d_min) ? p : best), f[0]).survival;
      const t = loss / (gain + loss);
      return { go: s > t, survival: s, threshold: t, reason: s > t ? "The window is likely long enough." : "The window is probably too short. Waiting.", locked: false };
    }),

  putMemory: (markdown: string, base_revision: number) =>
    write<{ revision: number }>("/memory", "PUT", { markdown, base_revision }, () => {
      if (base_revision !== demo.memory.revision) {
        throw new ApiError(409, "stale_revision", `The file is at revision ${demo.memory.revision}, not ${base_revision}.`);
      }
      const rev = demo.memory.revision + 1;
      const parsed = parseMemory(markdown, demo.memory.sections);
      demo.memory = toMemory(demo.memory.path, serializeMemory(parsed.role || "benefits-processor", rev, parsed.sections), parsed.sections);
      return { revision: rev };
    }),

  forget: (line_id: string) =>
    write<{ revision: number }>("/memory/forget", "POST", { line_id }, () => {
      for (const [name, lines] of Object.entries(demo.memory.sections)) {
        const l = lines.find((x) => x.id === line_id);
        if (l) {
          const md = removeLineText(demo.memory.markdown, l.text);
          if (md) {
            const rev = demo.memory.revision + 1;
            const next = { ...demo.memory.sections, [name]: lines.filter((x) => x.id !== line_id) };
            demo.memory = toMemory(demo.memory.path, serializeMemory(parseMemory(md).role || "benefits-processor", rev, next), next);
            return { revision: rev };
          }
        }
      }
      throw new ApiError(404, "no_such_line", "That line is not in the memory file any more.");
    }),

  decideProposal: (id: string, action: "approve" | "reject") =>
    write<RuleProposal>(`/memory/proposals/${encodeURIComponent(id)}/${action}`, "POST", undefined, () => {
      const p = demo.proposals.find((x) => x.id === id);
      if (!p) throw new ApiError(404, "no_such_proposal", "That rule proposal is gone.");
      p.status = action === "approve" ? "active" : "rejected";
      if (action === "approve") {
        p.version += 1;
        const key = p.kind === "procedure" ? "Procedure" : "Preferences";
        const next = { ...demo.memory.sections, [key]: [...(demo.memory.sections[key] ?? []), { id: `mem_rule_${p.id}`, text: p.rule, note: `proposed, accepted ${new Date().toISOString().slice(0, 10)}` }] };
        const rev = demo.memory.revision + 1;
        demo.memory = toMemory(demo.memory.path, serializeMemory("benefits-processor", rev, next), next);
      }
      return clone(p);
    }, action === "approve" ? "worker_approval" : "worker"),

  deleteWorkNode: async (node: { id: string; type: string; memory_line_id: string | null }): Promise<void> => {
    if (node.type === "memory" || (node.type === "skill" && node.memory_line_id)) {
      if (node.memory_line_id) {
        await api.forget(node.memory_line_id);
        demo.workDeleted.add(node.id);
        return;
      }
    }
    if (node.type === "routine" || node.type === "automation") {
      await api.setConsent(node.id.replace(/^(routine|automation):/, "").replace(/^auto-/, ""), { mode: "never" }).catch(() => undefined);
    }
    demo.workDeleted.add(node.id);
  },

  async onboard(role: string, answers: OnboardingAnswers, questions: OnboardingQuestions | undefined): Promise<{ result: OnboardingResult; source: "live" | "demo" }> {
    const wire = { ...answers, hours: { ...answers.hours, days: dayKeys(answers.hours.days as unknown as number[]) } };
    const r = await write<OnboardingResult>("/onboarding", "POST", { role, answers: wire }, () => {
      const md = buildPreview(role, questions, answers).text;
      return {
        person: "p_you",
        role,
        revision: 1,
        memory_markdown: md + "\n",
        risk_classes: questions?.pack.risk_classes ?? { irreversible: [] },
        tone: { length: answers.tone, voice: questions?.pack.tone_defaults.voice ?? "plain" },
        pace: answers.pace,
      };
    });
    return { result: r.data, source: r.source };
  },
};

/** Publish the pending-queue count for the nav badge. */
export async function refreshQueueBadge(): Promise<void> {
  try {
    const q = await api.queue("pending");
    setState({ pendingQueue: q.data.filter((x) => x.status === "pending").length });
  } catch {
    /* the badge is optional */
  }
}
