// Data for the Repeats page. A small client of its own (the shared api.ts has no hit list yet), in the same style as Growth/data.ts:
// reads `GET /hitlist` and `GET /hitlist/firm`, writes hide, unhide and reset as the worker. When the engine is down, the hit list layer is
// off (404 extension_off) or the route is missing, the example week answers instead and the page says so ("example data").
import { AGENT_URL, ApiError, ENGINE_URL, api, type Loaded } from "../../api";
import { classify, type Fallback } from "../../lib/fallback";
import { ROLE_HEADER } from "../../components/firm/net";
import { requestBody, requestHeaders } from "../../lib/http";
import { getState, noteSource } from "../../store";
import type { AnalyticMeta } from "../../types";
import { EXAMPLE_META, exampleFirm, exampleHitlist, type ExampleKind } from "../../fixtures/repeats";
import type { FirmWire, HitStatus, HitlistWire } from "../../components/repeats/types";

const WHO = { service: "The engine", flag: "UNDERSTUDY_X_HITLIST" };
const TIMEOUT_MS = 40_000;

type Reached = { reached: true; status: number; body: unknown } | { reached: false };

async function call(path: string, method: "GET" | "POST" = "GET", payload?: unknown, extra?: Record<string, string>): Promise<Reached> {
  const ctl = new AbortController();
  const timer = window.setTimeout(() => ctl.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(`${ENGINE_URL}${path}`, { method, signal: ctl.signal, headers: extra ? { ...(requestHeaders(method) ?? {}), ...extra } : requestHeaders(method), body: requestBody(method, payload) });
    let body: unknown = null;
    try { body = await res.json(); } catch { body = null; }
    return { reached: true, status: res.status, body };
  } catch {
    return { reached: false };
  } finally {
    window.clearTimeout(timer);
  }
}

const codeOf = (r: Reached): string | null => (r.reached ? ((r.body as { error?: { code?: string } } | null)?.error?.code ?? null) : null);
/** A 404 that is not "this person is unknown" means the engine has no such route: the layer is off or older than this page. */
const isMissing = (r: Reached) => !r.reached || r.status >= 500 || (r.status === 404 && codeOf(r) !== "unknown_person") || r.status === 405 || r.status === 501;
const failure = (r: Reached) => ({ reached: r.reached, status: r.reached ? r.status : undefined, body: r.reached ? r.body : undefined });

/** Why the page shows example data. The engine's own wording for a missing route varies, so a missing route is always "switched off", in our words. */
function whyFor(r: Reached): Fallback {
  if (r.reached && r.status === 404) {
    return { kind: "extension_off", status: 404, code: codeOf(r), message: `This feature is switched off in ${WHO.service}. Start it with ${WHO.flag}=1 (or UNDERSTUDY_X=1 for every extension) to see your own data. Until then Knack shows example data.` };
  }
  return classify(failure(r), WHO);
}

function errorOf(r: Reached & { reached: true }): ApiError {
  const e = (r.body as { error?: { code?: string; message?: string } } | null)?.error;
  return new ApiError(r.status, e?.code ?? `http_${r.status}`, e?.message ?? `The engine answered with status ${r.status}.`);
}

function envelope<T>(body: unknown): { data: T; meta: AnalyticMeta | null } {
  const b = body as { data?: T; meta?: AnalyticMeta } | null;
  return { data: (b?.data ?? (body as T)) as T, meta: b?.meta ?? null };
}

/* -- The example week, as the worker changes it this session ---------------------------------- */
const demo = { hidden: new Set<string>(), reset: false, status: {} as Record<string, HitStatus> };
export function restoreExample(): void { demo.hidden.clear(); demo.reset = false; demo.status = {}; }

/** `?example=` on the page (only used when the engine is not answering) previews every state the page can be in. */
const KINDS = ["new_user", "too_little_data", "nothing_repeats", "all_handled", "counting_again", "capture_off"] as const;
export const exampleKind = (q: string | null): ExampleKind | null => (q && (KINDS as readonly string[]).includes(q) ? (q as ExampleKind) : null);

export async function loadRepeats(windowDays: 7 | 30, kind: ExampleKind | null = null): Promise<Loaded<HitlistWire>> {
  const person = getState().person;
  const ask = (p: string | null) => call(`/hitlist?${new URLSearchParams({ window: String(windowDays), ...(p ? { person: p } : {}) })}`);
  let r = await ask(person);
  if (person && r.reached && r.status === 404 && codeOf(r) === "unknown_person") r = await ask(null);          // a stale identity: let the engine use its own default
  if (isMissing(r)) {
    noteSource("demo");
    return { data: exampleHitlist(windowDays, { hidden: demo.hidden, reset: demo.reset, status: demo.status, kind: kind ?? undefined }), meta: { ...EXAMPLE_META },
      source: "demo", why: whyFor(r) };
  }
  if (r.reached && r.status >= 400) throw errorOf(r);
  noteSource("live");
  return { ...envelope<HitlistWire>(r.reached ? r.body : null), source: "live", why: null };
}

/**
 * The firm's repeated work: the ADMIN's read (Automation). The engine gates it with the admin role and the per-boot token (the dev proxy adds the token), so this
 * is the one call here that sends the role header. A worker's screens (Routines, Needs you, Home) never call it: they read /hitlist, the person's own.
 */
export async function loadFirm(windowDays: 7 | 30): Promise<Loaded<FirmWire>> {
  const r = await call(`/hitlist/firm?window=${windowDays}`, "GET", undefined, { [ROLE_HEADER]: "admin" });
  if (isMissing(r)) {
    noteSource("demo");
    return { data: exampleFirm(windowDays), meta: { ...EXAMPLE_META, n: 60, n_unit: "people", note: "A made-up firm of about 60 people in three roles, not real people." }, source: "demo", why: whyFor(r) };
  }
  if (r.reached && r.status >= 400) throw errorOf(r);
  noteSource("live");
  return { ...envelope<FirmWire>(r.reached ? r.body : null), source: "live", why: null };
}

/* -- The worker's own writes: hide, bring back, start counting again, watch first ------------- */
async function write(path: string, payload: unknown): Promise<void> {
  const r = await call(path, "POST", payload);
  if (!r.reached) throw new ApiError(0, "engine_down", "The engine did not answer, so nothing changed. Try again in a moment.");
  if (r.status >= 400) throw errorOf(r);
}

export async function hideRow(id: string, windowDays: number, source: "live" | "demo"): Promise<void> {
  if (source === "demo") { demo.hidden.add(id); return; }
  await write("/hitlist/hide", { id, window: windowDays });
}

export async function unhideRow(id: string, source: "live" | "demo"): Promise<void> {
  if (source === "demo") { demo.hidden.delete(id); return; }
  await write("/hitlist/unhide", { id });
}

/** Start counting again. The engine clears the hit list's own counts and hide marks and nothing else. */
export async function resetCounts(source: "live" | "demo"): Promise<void> {
  if (source === "demo") { demo.reset = true; demo.hidden.clear(); return; }
  await write("/hitlist/reset", {});
}

/** The first, safest step of Automate: watch first. It practises on the worker's next cases and compares; nothing is saved or sent. */
export async function watchFirst(rowId: string, routineId: string, source: "live" | "demo", override = false): Promise<void> {
  if (source === "demo") { demo.status[rowId] = "learning"; return; }
  await api.setConsent(routineId, { mode: "shadow", ...(override ? { skill_override: true } : {}) });
}

/* -- Run now: the agent service's own route, POST /routines/{id}/run ------------------------------------------------------------------ */
const AGENT_MODE: Record<string, "shadow" | "approved" | "background"> = { shadow: "shadow", approval: "approved", unattended: "background" };

/** How a routine starts from its current consent: watching practises, asks-first runs with approval, away runs in the background. */
export const runModeOf = (status: string): "shadow" | "approved" | "background" | null => AGENT_MODE[status] ?? null;

/**
 * Start the routine in its current mode on the agent service (sandbox sites, never the worker's real screen). The agent answers 409 when the consent
 * does not allow it and says why; that sentence is shown as it is. Returns null when the agent service did not answer: nothing started.
 */
export async function runNow(routineId: string, status: string): Promise<{ run_id: string } | null> {
  const mode = runModeOf(status);
  if (!mode) throw new ApiError(409, "not_running", "This routine is not switched on, so there is nothing to run.");
  let res: Response;
  try {
    res = await fetch(`${AGENT_URL}/routines/${encodeURIComponent(routineId)}/run`, { method: "POST", headers: requestHeaders("POST", "worker"), body: requestBody("POST", { mode }) });
  } catch { return null; }
  let body: unknown = null;
  try { body = await res.json(); } catch { body = null; }
  if (res.status === 404 || res.status === 405 || res.status === 501 || res.status >= 502) return null;
  if (res.status >= 400) {
    const d = body as { detail?: unknown; error?: { message?: string } } | null;
    const msg = typeof d?.detail === "string" ? d.detail : d?.error?.message;
    throw new ApiError(res.status, `http_${res.status}`, msg ?? `The agent service answered with status ${res.status}. Nothing started.`);
  }
  return { run_id: (body as { run_id?: string } | null)?.run_id ?? "" };
}

export type { Fallback };
