import { noteSource, setState } from "./store";
import type {
  Analytic, AnalyticMeta, AuditLine, CoachState, EvalReport, Genome, Hazard, Health, KillState, Memory,
  OffhoursReport, OnboardingAnswers, OnboardingQuestions, OnboardingResult, Pack, Presence, QueueItem, QuietHours,
  Replay, Routine, RuleProposal, Transitions, WorkGraph,
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
import { parseMemory, removeLineText, serializeMemory, toMemory } from "./lib/memory";
import { buildPreview } from "./lib/memoryPreview";
import { idleCapacity } from "./lib/heatmap";

export const ENGINE_URL: string = (import.meta.env.VITE_ENGINE_URL as string | undefined) ?? "http://127.0.0.1:7700";
export const AGENT_URL: string = (import.meta.env.VITE_AGENT_URL as string | undefined) ?? "http://127.0.0.1:7710";
const TIMEOUT_MS = 2500;

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

type Reached = { reached: true; status: number; body: unknown } | { reached: false };

/** After a network failure, skip that service for a few seconds: faster screens, no console spam. */
const downUntil = new Map<string, number>();
const BACKOFF_MS = 6000;
export function forgetBackoff(): void { downUntil.clear(); }

async function send(base: string, path: string, method: string, payload?: unknown, force = false): Promise<Reached> {
  if (!force && (downUntil.get(base) ?? 0) > Date.now()) return { reached: false };
  const ctl = new AbortController();
  const timer = window.setTimeout(() => ctl.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(`${base}${path}`, {
      method,
      signal: ctl.signal,
      headers: payload !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: payload !== undefined ? JSON.stringify(payload) : undefined,
    });
    let body: unknown = null;
    try { body = await res.json(); } catch { body = null; }
    return { reached: true, status: res.status, body };
  } catch {
    downUntil.set(base, Date.now() + BACKOFF_MS);
    return { reached: false };
  } finally {
    window.clearTimeout(timer);
  }
}

function toApiError(status: number, body: unknown): ApiError {
  const e = (body as { error?: { code?: string; message?: string } } | null)?.error;
  return new ApiError(status, e?.code ?? `http_${status}`, e?.message ?? `The service answered with status ${status}.`);
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
async function write<T>(path: string, method: "POST" | "PUT", payload: unknown, fallback: () => T, base = ENGINE_URL): Promise<{ data: T; source: "live" | "demo" }> {
  const r = await send(base, path, method, payload);
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

  presence: (person?: string) =>
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

  packs: () => read<Pack[]>("/packs", () => ({ data: fx<Pack[]>(packsFx) })),

  onboardingQuestions: (role: string) =>
    read<OnboardingQuestions>(`/onboarding/questions?role=${encodeURIComponent(role)}`, () => ({
      data: fx<Record<string, OnboardingQuestions>>(onboardingFx)[role] ?? fx<Record<string, OnboardingQuestions>>(onboardingFx)["benefits-processor"],
    })),

  hazard: (person = "p_novice_03") => read<Hazard>(`/hazard/${encodeURIComponent(person)}`, () => ({ data: dataOf<Hazard>(hazardFx), meta: metaOf(hazardFx) })),

  evalReport: () =>
    read<EvalReport>("/eval/report", () => ({ data: fx<EvalReport>(evalFx), meta: null })),

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

  setConsent: (id: string, body: { mode: string; irreversible_unattended?: string[]; typed_confirm?: string }) =>
    write<Routine>(`/routines/${encodeURIComponent(id)}/consent`, "POST", { irreversible_unattended: [], typed_confirm: "", ...body }, () => {
      const r = demo.routines.find((x) => x.id === id);
      if (!r) throw new ApiError(404, "no_such_routine", `There is no routine called ${id}.`);
      const irreversible = body.irreversible_unattended ?? [];
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

  setQueue: (id: string, action: "approve" | "reject") =>
    write<QueueItem>(`/queue/${encodeURIComponent(id)}/${action}`, "POST", undefined, () => {
      const q = demo.queue.find((x) => x.id === id);
      if (!q) throw new ApiError(404, "no_such_item", `There is no queue item ${id}.`);
      q.status = action === "approve" ? "approved" : "rejected";
      q.decided_at = new Date().toISOString();
      q.decided_by = "human";
      return clone(q);
    }),

  putQuietHours: (q: QuietHours) =>
    write<QuietHours>("/presence/quiet_hours", "PUT", q, () => {
      demo.quiet = clone(q);
      return clone(q);
    }),

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
    }),

  deleteWorkNode: async (node: { id: string; type: string; memory_line_id: string | null }): Promise<void> => {
    if (node.type === "memory" || (node.type === "skill" && node.memory_line_id)) {
      if (node.memory_line_id) {
        await api.forget(node.memory_line_id);
        demo.workDeleted.add(node.id);
        return;
      }
    }
    if (node.type === "routine" || node.type === "automation") {
      await api.setConsent(node.id.replace(/^auto-/, ""), { mode: "never" }).catch(() => undefined);
    }
    demo.workDeleted.add(node.id);
  },

  async onboard(role: string, answers: OnboardingAnswers, questions: OnboardingQuestions | undefined): Promise<{ result: OnboardingResult; source: "live" | "demo" }> {
    const r = await write<OnboardingResult>("/onboarding", "POST", { role, answers }, () => {
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
