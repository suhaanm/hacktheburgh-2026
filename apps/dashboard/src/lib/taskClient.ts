// The calls the Home task box makes to Track T's task service (task API contract v1, through the dashboard's /agent proxy, which adds the per-boot token).
// Every write carries JSON and the actor header, from lib/http.ts. A consent is sent as `worker_approval` and nothing else is. The service being absent (no
// connection, or the proxy has nothing behind it) is its own answer, "unavailable": the box then says nothing was started. Pure of React; `fetch` is the only
// outside thing, so the tests stub it.
import { AGENT_URL } from "../api";
import { MISSING_HEADER, notReadyReason, requestBody, requestHeaders, type Actor } from "./http";
import { parseSubmitted, sendError, type ConsentChoice, type Submitted, type TaskSource } from "./taskbox";

export type Reply = { kind: "ok"; status: number; body: unknown } | { kind: "unavailable" } | { kind: "refused"; status: number; code: string | null; message: string | null };

const TIMEOUT_MS = 30_000;

async function call(path: string, method: "GET" | "POST", payload: unknown, actor?: Actor, retried = false): Promise<Reply> {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(`${AGENT_URL}${path}`, { method, signal: ctl.signal, headers: requestHeaders(method, actor), body: requestBody(method, payload) });
    let body: unknown = null;
    try { body = await res.json(); } catch { body = null; }
    const err = (body as { error?: { code?: string; message?: string } } | null)?.error;
    // A service that restarted wrote a new token between our request and its answer: ask once more (the proxy reads the file afresh).
    if (!retried && res.status === 403 && method !== "GET" && err?.code === "token_invalid") return call(path, method, payload, actor, true);
    if (res.ok) return { kind: "ok", status: res.status, body };
    // The proxy has nothing behind it (502, 503, 504), or this service has no such route: it is not running as far as the worker is concerned.
    if (res.status === 502 || res.status === 503 || res.status === 504 || (res.status === 404 && !err)) return { kind: "unavailable" };
    const notReady = notReadyReason(res.status, err?.code, res.headers.get(MISSING_HEADER) === "missing");
    return { kind: "refused", status: res.status, code: err?.code ?? null, message: notReady ?? err?.message ?? null };
  } catch {
    return { kind: "unavailable" };
  } finally {
    clearTimeout(timer);
  }
}

export type SubmitResult = { kind: "placed"; sub: Submitted } | { kind: "unavailable" } | { kind: "error"; message: string };

/** Sends a task the worker typed or said. Never called with nothing: the caller has run checkTask. */
export async function submitTask(text: string, source: TaskSource = "typed"): Promise<SubmitResult> {
  const r = await call("/tasks", "POST", { text, source }, "worker");
  if (r.kind === "unavailable") return { kind: "unavailable" };
  if (r.kind === "refused") return { kind: "error", message: sendError(r.status, r.code, r.message) };
  const sub = parseSubmitted(r.body);
  return sub ? { kind: "placed", sub } : { kind: "error", message: sendError(null, null, null) };
}

export type Decision = { kind: "done" } | { kind: "unavailable" } | { kind: "error"; message: string };

const decision = (r: Reply): Decision => (r.kind === "ok" ? { kind: "done" } : r.kind === "unavailable" ? { kind: "unavailable" } : { kind: "error", message: sendError(r.status, r.code, r.message) });

/** The worker's answer to a consent card. A real click on one of the card's own buttons, sent as the approval actor. */
export const decideConsent = async (id: string, choice: ConsentChoice): Promise<Decision> => decision(await call(`/tasks/${encodeURIComponent(id)}/consent`, "POST", { choice }, "worker_approval"));

/** The worker's answer to a question card. */
export const answerQuestion = async (id: string, optionId: string): Promise<Decision> => decision(await call(`/tasks/${encodeURIComponent(id)}/answer`, "POST", { option_id: optionId }, "worker"));

export interface TaskNow { state: string; answer: string | null; result: string | null; latest: string | null; reason: string | null }

const text = (v: unknown, max: number): string | null => (typeof v === "string" && v.trim() ? v.trim().slice(0, max) : null);

/** One task as it is now (GET /tasks/{id}); `answer` is the full text of an inline answer once the task is done. Null when the service does not answer. */
export async function readTask(id: string): Promise<TaskNow | null> {
  const r = await call(`/tasks/${encodeURIComponent(id)}`, "GET", undefined);
  if (r.kind !== "ok" || !r.body || typeof r.body !== "object") return null;
  const o = ("data" in (r.body as object) && (r.body as { data?: unknown }).data && typeof (r.body as { data?: unknown }).data === "object" ? (r.body as { data: unknown }).data : r.body) as Record<string, unknown>;
  return { state: typeof o.state === "string" ? o.state : "", answer: text(o.answer, 1500), result: text(o.result, 140), latest: text(o.latest, 100), reason: text(o.reason, 140) };
}
