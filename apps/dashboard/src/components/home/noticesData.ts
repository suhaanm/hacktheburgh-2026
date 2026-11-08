// The worker's own notices data: what the attention layer learned about how loudly to speak. Export and delete, as the worker.
// A small client of its own (the shared api.ts has no DELETE). In example mode (engine down, layer off, route missing) it acts on the example only and says so.
import { ApiError, ENGINE_URL } from "../../api";
import { requestBody, requestHeaders } from "../../lib/http";
import { envelope, isMissing, qs, type Reached } from "../growth/net";
import attentionSettingsFx from "../../fixtures/attention-settings.json";

async function call(path: string, method: "GET" | "DELETE"): Promise<Reached> {
  const ctl = new AbortController();
  const timer = window.setTimeout(() => ctl.abort(), 20_000);
  try {
    const res = await fetch(`${ENGINE_URL}${path}`, { method, signal: ctl.signal, headers: requestHeaders(method), body: requestBody(method, undefined) });
    let body: unknown = null;
    try { body = await res.json(); } catch { body = null; }
    return { reached: true, status: res.status, body };
  } catch {
    return { reached: false };
  } finally {
    window.clearTimeout(timer);
  }
}

function errorOf(r: Reached & { reached: true }): ApiError {
  const e = (r.body as { error?: { code?: string; message?: string } } | null)?.error;
  return new ApiError(r.status, e?.code ?? `http_${r.status}`, e?.message ?? `The engine answered with status ${r.status}.`);
}

/** The engine is there and the layer is on, but nobody is set up yet: a real, empty answer, not a missing feature. */
const unknownPerson = (r: Reached): boolean => r.reached && r.status === 404 && (r.body as { error?: { code?: string } } | null)?.error?.code === "unknown_person";

let exampleCleared = false;
export const isExampleCleared = (): boolean => exampleCleared;
export const restoreExampleNotices = (): void => { exampleCleared = false; };

export interface NoticesFile { filename: string; text: string; example: boolean }

/** The notices data as the engine would export it. In example mode, the example settings, labelled. */
export async function exportNotices(person: string | null): Promise<NoticesFile> {
  const stamp = new Date().toISOString().slice(0, 10);
  const filename = `understudy-notices-${stamp}.json`;
  const r = await call(`/attention/export${qs({ person })}`, "GET");
  if (unknownPerson(r)) return { filename, text: JSON.stringify({ origin: "live", settings: null, note: "Nothing is stored yet." }, null, 2), example: false };
  if (isMissing(r)) {
    const body = exampleCleared ? { origin: "example data", settings: null } : { origin: "example data", settings: envelope<unknown>(attentionSettingsFx).data };
    return { filename, text: JSON.stringify(body, null, 2), example: true };
  }
  if (r.reached && r.status >= 400) throw errorOf(r);
  return { filename, text: JSON.stringify(r.reached ? r.body : null, null, 2), example: false };
}

/** Delete the notices data: what was learned about how loudly to speak. Returns how many records were removed and whether it was only the example. */
export async function deleteNotices(person: string | null): Promise<{ deleted: number; example: boolean }> {
  const r = await call(`/attention${qs({ person })}`, "DELETE");
  if (unknownPerson(r)) return { deleted: 0, example: false };
  if (isMissing(r)) {
    const had = exampleCleared ? 0 : 1;
    exampleCleared = true;
    return { deleted: had, example: true };
  }
  if (r.reached && r.status >= 400) throw errorOf(r);
  const n = (r.reached ? (r.body as { deleted?: number } | null)?.deleted : 0) ?? 0;
  return { deleted: typeof n === "number" ? n : 0, example: false };
}
