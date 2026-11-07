// The small client for the /insights/* routes. It follows the Growth screen's pattern (its own fetch, example data when the engine is
// down, the layer is off or the route is missing) and adds the one thing the shared client does not: the demo role header on admin reads.
//
// The page never holds the per-boot token. The dev server adds it on the way through (vite.proxy.ts); the engine then checks BOTH the
// role header and the token on every admin request (INSIGHTS, 7 Nov), so the header alone proves nothing.
import { ApiError, ENGINE_URL, type Loaded } from "../../api";
import { classify, type Fallback } from "../../lib/fallback";
import { MISSING_HEADER, requestBody, requestHeaders } from "../../lib/http";
import { noteSource } from "../../store";
import type { AnalyticMeta } from "../../types";
import { envelope, failure, isMissing, qs, type Reached } from "../growth/net";

export const ROLE_HEADER = "x-understudy-role";
export type Audience = "worker" | "admin";
export const INSIGHTS_WHO = { service: "The engine", flag: "UNDERSTUDY_X_INSIGHTS" };
const TIMEOUT_MS = 40_000;

export { qs };

/** The headers of a read: the admin role claim on admin routes, nothing on worker routes (those never return admin data). */
export const readHeaders = (audience: Audience): Record<string, string> | undefined => (audience === "admin" ? { [ROLE_HEADER]: "admin" } : undefined);

/** A refused request in plain words. Null for any other status, which keeps the engine's own message. */
export function refusalText(status: number, code: string | undefined, tokenMissing = false): string | null {
  if (status !== 403) return null;
  if (code === "admin_token_required" || tokenMissing || (code && /token/i.test(code))) {
    return "The engine did not receive this page's start-up token, so it will not show the firm. Restart everything with `make dev`, wait for it to say it is running, then try again. Nothing was changed.";
  }
  if (code === "admin_actor_refused" || code === "worker_actor_required") return "The engine only answers this for the person at the keyboard, not for a script or an agent. Nothing was shown and nothing was changed.";
  if (code === "admin_only") return "The engine shows this only to the Admin role. Choose the Admin view in the menu, then try again.";
  return null;
}

type Raw = Reached & { tokenMissing?: boolean };

async function call(path: string, method: "GET" | "POST", audience: Audience, payload?: unknown): Promise<Raw> {
  const ctl = new AbortController();
  const timer = window.setTimeout(() => ctl.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(`${ENGINE_URL}${path}`, {
      method, signal: ctl.signal, body: requestBody(method, payload),
      headers: { ...(requestHeaders(method) ?? {}), ...(readHeaders(audience) ?? {}) },
    });
    let body: unknown = null;
    try { body = await res.json(); } catch { body = null; }
    return { reached: true, status: res.status, body, tokenMissing: res.headers.get(MISSING_HEADER) === "missing" };
  } catch {
    return { reached: false };
  } finally {
    window.clearTimeout(timer);
  }
}

function errorOf(r: Raw & { reached: true }): ApiError {
  const e = (r.body as { error?: { code?: string; message?: string } } | null)?.error;
  const refused = refusalText(r.status, e?.code, r.tokenMissing);
  return new ApiError(r.status, e?.code ?? `http_${r.status}`, refused ?? e?.message ?? `The engine answered with status ${r.status}.`);
}

const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x)) as T;
const metaOf = (body: unknown): AnalyticMeta | null => {
  const m = body && typeof body === "object" ? (body as { meta?: unknown }).meta : null;
  return m && typeof m === "object" ? (m as AnalyticMeta) : null;
};

/**
 * A read. `fixture` returns the example body (`{meta, data}` or bare) for when the engine cannot answer; `normalise` turns either
 * kind of body into the screen's shape. A 403 and other refusals are errors to read, never quietly swapped for example data.
 */
export async function insightRead<T>(path: string, audience: Audience, fixture: () => unknown, normalise: (body: unknown) => T, opts: { unknownPerson?: () => unknown } = {}): Promise<Loaded<T>> {
  const r = await call(path, "GET", audience);
  // The engine is there and the layer is on, but nobody is set up yet: that is a real, empty answer, not a missing feature or example data.
  if (opts.unknownPerson && r.reached && r.status === 404 && (r.body as { error?: { code?: string } } | null)?.error?.code === "unknown_person") {
    noteSource("live");
    return { data: normalise(opts.unknownPerson()), meta: null, source: "live", why: null };
  }
  if (isMissing(r)) {
    const why: Fallback = classify(failure(r), INSIGHTS_WHO);
    const fx = clone(fixture());
    noteSource("demo");
    return { data: normalise(fx), meta: metaOf(fx), source: "demo", why };
  }
  if (r.reached && r.status >= 400) throw errorOf(r as Raw & { reached: true });
  noteSource("live");
  const body = r.reached ? r.body : null;
  return { data: normalise(envelope<unknown>(body).data), meta: metaOf(body), source: "live", why: null };
}

/** A write as the worker. Example mode answers locally and says so (`source: "demo"`). A refusal throws. */
export async function insightWrite(path: string, payload: unknown): Promise<{ source: "live" | "demo" }> {
  const r = await call(path, "POST", "worker", payload);
  if (!r.reached || r.status === 404 || r.status === 405 || r.status === 501) { noteSource("demo"); return { source: "demo" }; }
  if (r.status >= 400) throw errorOf(r as Raw & { reached: true });
  noteSource("live");
  return { source: "live" };
}
