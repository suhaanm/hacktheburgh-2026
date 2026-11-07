// Pure pieces of the Growth client: what counts as "the service is not there", how a failure is described for the
// example-data note, and how a query string and an envelope are read. No fetch here, so it is tested without a network.
import type { Envelope, GrowthMeta } from "./wire";

export type Reached = { reached: true; status: number; body: unknown } | { reached: false };

/** The service is down, or has no such route: the screen shows example data. */
export const isMissing = (r: Reached): boolean => !r.reached || r.status === 404 || r.status === 405 || r.status === 501 || r.status >= 500;

/**
 * Describe a failed read for the example-data note. A bare "no such route" 404 is a missing route, not a complaint, so the body is
 * dropped and the note stays calm. Only an explicit "feature switched off" keeps its own words.
 */
export function failure(r: Reached): { reached: boolean; status?: number; body?: unknown } {
  if (!r.reached) return { reached: false };
  const code = (r.body as { error?: { code?: string } } | null)?.error?.code;
  const plain404 = r.status === 404 && code !== "extension_off" && code !== "extension_disabled";
  return { reached: true, status: r.status, body: plain404 ? undefined : r.body };
}

export function qs(p: Record<string, string | null | undefined>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(p)) if (v) q.set(k, v);
  const t = q.toString();
  return t ? `?${t}` : "";
}

/** Accept both `{ meta, data }` and a bare body. */
export function envelope<T>(body: unknown): Envelope<T> {
  if (body && typeof body === "object" && "data" in body) {
    const b = body as { meta?: GrowthMeta | null; data: T };
    return { meta: b.meta ?? null, data: b.data };
  }
  return { meta: null, data: body as T };
}
