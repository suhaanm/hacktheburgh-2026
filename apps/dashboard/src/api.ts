import { noteSource, setState } from "./store";
import type { ApprovalAuth } from "./auth/types";
import type {
  Analytic, AnalyticMeta, AuditLine, CoachState, EvalReport, Genome, Hazard, Health, KillState, Memory,
  AgentRun, AgentRunDetail, Briefing, CalSuggestion, CalendarWeek, CoachDecision, CoachOutcome, LedgerEntry, LocalModelStatus, OffhoursReport, OnboardingAnswers, OnboardingQuestions, OnboardingResult, Pack, Presence, QueueItem, QuietHours,
  PrivacySummary, Prepared, Replay, Routine, RuleProposal, SpawnKind, Transitions, WorkGraph,
} from "./types";
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
import { parseMemory, removeLineText, serializeMemory, toMemory } from "./lib/memory";
import { buildPreview } from "./lib/memoryPreview";
import { idleCapacity } from "./lib/heatmap";
import { dayKeys, normDays } from "./lib/days";

export const ENGINE_URL: string = (import.meta.env.VITE_ENGINE_URL as string | undefined) ?? "http://127.0.0.1:7700";
export const AGENT_URL: string = (import.meta.env.VITE_AGENT_URL as string | undefined) ?? "http://127.0.0.1:7710";
/** The first calls to a cold engine are slow (a genome about 3 s, routines about 7 s, a hazard 6 to 12 s). Only a hung connection hits this. */
const TIMEOUT_MS = 40_000;

/** Writes carry who is acting. The engine refuses anything but the worker's own UI (403 write_refused). */
export type Actor = "worker" | "worker_approval";

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
}

const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x)) as T;
const fx = <T,>(x: unknown) => x as T;

/** Accept both `{meta, data}` and a bare body, so a service that skips the envelope still works. */
function unwrap<T>(body: unknown): { data: T; meta: AnalyticMeta | null } {
  if (body && typeof body === "object" && !Array.isArray(body) && "data" in body && "meta" in body) {
    const b = body as Analytic<T>;
    return { data: b.data, meta: b.meta };
  }
  return { data: body as T, meta: null };
}

type Reached = { reached: true; status: number; body: unknown } | { reached: false; timedOut?: boolean };

/** After a network failure, skip that service for a few seconds: faster screens, no console spam. */
const downUntil = new Map<string, number>();
const BACKOFF_MS = 6000;
export function forgetBackoff(): void { downUntil.clear(); }

async function send(base: string, path: string, method: string, payload?: unknown, force = false, actor?: Actor): Promise<Reached> {
  if (!force && (downUntil.get(base) ?? 0) > Date.now()) return { reached: false };
  const ctl = new AbortController();
  let timedOut = false;
  const timer = window.setTimeout(() => { timedOut = true; ctl.abort(); }, TIMEOUT_MS);
  try {
    const headers: Record<string, string> = {};
    if (payload !== undefined) headers["Content-Type"] = "application/json";
    if (actor) headers["X-Understudy-Actor"] = actor;
    const res = await fetch(`${base}${path}`, {
      method,
      signal: ctl.signal,
      headers: Object.keys(headers).length ? headers : undefined,
      body: payload !== undefined ? JSON.stringify(payload) : undefined,
    });
    let body: unknown = null;
    try { body = await res.json(); } catch { body = null; }
    return { reached: true, status: res.status, body };
  } catch {
    // A refused connection means the service is down: skip it for a few seconds. A timeout means it is slow, not gone.
    if (!timedOut) downUntil.set(base, Date.now() + BACKOFF_MS);
    return { reached: false, timedOut };
  } finally {
    window.clearTimeout(timer);
  }
}

function toApiError(status: number, body: unknown): ApiError {
  const e = (body as { error?: { code?: string; message?: string } } | null)?.error;
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

async function read<T>(path: string, fallback: () => { data: T; meta?: AnalyticMeta | null }, base = ENGINE_URL): Promise<Loaded<T>> {
  const r = await send(base, path, "GET");
  if (isMissing(r)) {
    noteSource("demo");
    const f = fallback();
    return { data: clone(f.data), meta: f.meta ? clone(f.meta) : null, source: "demo" };
  }
  if (r.reached && r.status >= 400) throw toApiError(r.status, r.body);
  noteSource("live");
  const u = unwrap<T>(r.reached ? r.body : null);
  return { ...u, source: "live" };
}

/** A write. When the service is down the demo state takes it, so the screen still works. */
async function write<T>(path: string, method: "POST" | "PUT", payload: unknown, fallback: () => T, actor: Actor = "worker", base = ENGINE_URL): Promise<{ data: T; source: "live" | "demo" }> {
  const r = await send(base, path, method, payload, false, actor);
  if (isMissing(r)) {
    noteSource("demo");
    return { data: fallback(), source: "demo" };
  }
  if (r.reached && r.status >= 400) throw toApiError(r.status, r.body);
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
  calendarWeek: (person?: string) =>
    read<CalendarWeek>(`/calendar/week${person ? `?person=${encodeURIComponent(person)}` : ""}`, () => ({ data: dataOf<CalendarWeek>(weekFx), meta: metaOf(weekFx) })),

  calendarSuggestions: (person?: string) =>
    read<CalSuggestion[]>(`/calendar/suggestions${person ? `?person=${encodeURIComponent(person)}` : ""}`, () => ({ data: dataOf<CalSuggestion[]>(suggestionsFx), meta: metaOf(suggestionsFx) })),

  briefing: (person?: string) =>
    read<Briefing>(`/briefing${person ? `?person=${encodeURIComponent(person)}` : ""}`, () => ({ data: demo.briefing, meta: metaOf(briefingFx) })),

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
    read<AgentRun[]>(`/agents/runs${person ? `?person=${encodeURIComponent(person)}` : ""}`, () => ({ data: demo.runs, meta: metaOf(agentsFx) }), AGENT_URL),

  agentsRunDetail: (id: string) =>
    read<AgentRunDetail>(`/agents/runs/${encodeURIComponent(id)}`, () => ({ data: agentDetails[id] ?? { artifacts: [], result: null } }), AGENT_URL),

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
    read<LedgerEntry[]>(`/privacy/ledger?limit=${limit}`, () => ({ data: demo.ledger, meta: metaOf(ledgerFx) })),

  privacySummary: () =>
    read<PrivacySummary>("/privacy/summary", () => {
      const by: Record<string, number> = {};
      for (const e of demo.ledger) by[e.purpose] = (by[e.purpose] ?? 0) + 1;
      const base = dataOf<PrivacySummary>(privacySummaryFx);
      return { data: { ...base, calls: demo.ledger.length, by_purpose: by, last_call: demo.ledger[0]?.t ?? null }, meta: metaOf(privacySummaryFx) };
    }),

  privacyClear: () =>
    write<unknown>("/privacy/ledger/clear", "POST", undefined, () => { demo.ledger = []; return { ok: true }; }),

  localModel: () => read<LocalModelStatus>("/localmodel/status", () => ({ data: fx<LocalModelStatus>(localModelFx) })),

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
